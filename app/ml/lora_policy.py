"""LoRA adaptation for store-policy understanding (PyTorch + Hugging Face peft).

1. Pretrain a small byte-level Transformer encoder from scratch with masked-byte modelling on unlabelled
   shopping/finance text (no labels used).
2. Adapt it to classify policy sentences (8 clause types) four ways and compare on UNSEEN store styles:
     - LoRA (rank 4, 8, 16) on the attention query/value projections + classifier head  [peft]
     - full fine-tuning (every weight trainable)
     - head only (frozen encoder)
     - TF-IDF + logistic regression baseline (no neural network)
3. Save the best adapter; the policy expert uses it to find the right sentences, then plain code reads the numbers.

Run:  python -m app.ml.lora_policy   (≈5–10 min on a laptop CPU)
"""
from __future__ import annotations

import copy
import json
import math
import time

import numpy as np
import torch
from torch import nn

from ..config import MODEL_DIR
from . import policy_data

torch.manual_seed(0)
torch.set_num_threads(max(1, torch.get_num_threads()))
MAX_LEN, PAD, MASK, CLS = 128, 256, 257, 258
VOCAB = 259
R = lambda x: round(float(x), 3)  # noqa: E731


def encode(texts: list[str]) -> torch.Tensor:
    out = torch.full((len(texts), MAX_LEN), PAD, dtype=torch.long)
    for i, t in enumerate(texts):
        b = [CLS] + list(t.encode("utf-8")[: MAX_LEN - 1])
        out[i, : len(b)] = torch.tensor(b)
    return out


class Attention(nn.Module):
    def __init__(self, d: int, h: int):
        super().__init__()
        self.h, self.dk = h, d // h
        self.q_proj, self.k_proj, self.v_proj, self.o_proj = (nn.Linear(d, d) for _ in range(4))

    def forward(self, x, pad_mask):
        B, T, D = x.shape
        q = self.q_proj(x).view(B, T, self.h, self.dk).transpose(1, 2)
        k = self.k_proj(x).view(B, T, self.h, self.dk).transpose(1, 2)
        v = self.v_proj(x).view(B, T, self.h, self.dk).transpose(1, 2)
        att = (q @ k.transpose(-1, -2)) / math.sqrt(self.dk)
        att = att.masked_fill(pad_mask[:, None, None, :], float("-inf")).softmax(-1)
        return self.o_proj((att @ v).transpose(1, 2).reshape(B, T, D))


class Block(nn.Module):
    def __init__(self, d, h):
        super().__init__()
        self.att, self.n1, self.n2 = Attention(d, h), nn.LayerNorm(d), nn.LayerNorm(d)
        self.ff = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d))

    def forward(self, x, m):
        x = x + self.att(self.n1(x), m)
        return x + self.ff(self.n2(x))


class Encoder(nn.Module):
    def __init__(self, d=128, h=4, layers=3):
        super().__init__()
        self.emb, self.pos = nn.Embedding(VOCAB, d), nn.Embedding(MAX_LEN, d)
        self.blocks = nn.ModuleList(Block(d, h) for _ in range(layers))
        self.norm = nn.LayerNorm(d)

    def forward(self, ids):
        m = ids == PAD
        x = self.emb(ids) + self.pos(torch.arange(ids.shape[1]))[None]
        for b in self.blocks:
            x = b(x, m)
        return self.norm(x)


class MLM(nn.Module):
    def __init__(self, enc):
        super().__init__()
        self.enc, self.head = enc, nn.Linear(enc.norm.normalized_shape[0], VOCAB)

    def forward(self, ids):
        return self.head(self.enc(ids))


class Classifier(nn.Module):
    def __init__(self, enc, n_classes):
        super().__init__()
        d = enc.norm.normalized_shape[0]
        self.enc, self.classifier = enc, nn.Linear(d, n_classes)

    def forward(self, input_ids=None, **_):
        h = self.enc(input_ids)
        m = (input_ids != PAD).float()[..., None]
        return self.classifier((h * m).sum(1) / m.sum(1).clamp(min=1))  # mean over real bytes


def pretrain(epochs: int = 4, batch: int = 64, lr: float = 1e-3) -> tuple[Encoder, dict]:
    ids = encode(policy_data.pretrain_corpus(n=12000))
    model = MLM(Encoder())
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    losses = []
    for _ in range(epochs):
        perm = torch.randperm(len(ids))
        for i in range(0, len(ids), batch):
            x = ids[perm[i:i + batch]].clone()
            real = x != PAD
            pick = (torch.rand(x.shape) < 0.15) & real & (x != CLS)
            target = torch.where(pick, x, torch.full_like(x, -100))
            x[pick] = MASK
            loss = nn.functional.cross_entropy(model(x).reshape(-1, VOCAB), target.reshape(-1), ignore_index=-100)
            opt.zero_grad()
            loss.backward()
            opt.step()
            losses.append(loss.item())
    return model.enc, {"mlm_loss_start": R(np.mean(losses[:20])), "mlm_loss_end": R(np.mean(losses[-20:])),
                       "epochs": epochs, "batch": batch, "lr": lr, "texts": len(ids),
                       "encoder_params": sum(p.numel() for p in model.enc.parameters())}


def _train_clf(model, Xtr, ytr, Xva, yva, epochs, lr, batch=64):
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.01)
    best, best_state = -1.0, None
    for _ in range(epochs):
        model.train()
        perm = torch.randperm(len(Xtr))
        for i in range(0, len(Xtr), batch):
            j = perm[i:i + batch]
            loss = nn.functional.cross_entropy(model(input_ids=Xtr[j]), ytr[j])
            opt.zero_grad()
            loss.backward()
            opt.step()
        acc = _acc(model, Xva, yva)
        if acc > best:
            best, best_state = acc, copy.deepcopy(model.state_dict())
    model.load_state_dict(best_state)
    return best


@torch.no_grad()
def _predict(model, X):
    model.eval()
    return torch.cat([model(input_ids=X[i:i + 256]).argmax(-1) for i in range(0, len(X), 256)])


def _acc(model, X, y):
    return (_predict(model, X) == y).float().mean().item()


def _f1(model, X, y):
    from sklearn.metrics import f1_score

    return f1_score(y.numpy(), _predict(model, X).numpy(), average="macro")


def main() -> dict:
    from peft import LoraConfig, get_peft_model
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    from sklearn.pipeline import make_pipeline

    t0 = time.time()
    enc, pre = pretrain()
    Xtr_t, ytr_l = policy_data.augment(*policy_data.make("train", 200, seed=1), seed=1)
    Xva_t, yva_l = policy_data.make("dev", 40, seed=2)            # different style: rewards generalising, not memorising
    Xte_t, yte_l = policy_data.make("unseen", 60, seed=3)        # different store styles
    Xtr, Xva, Xte = encode(Xtr_t), encode(Xva_t), encode(Xte_t)
    ytr, yva, yte = (torch.tensor(v) for v in (ytr_l, yva_l, yte_l))
    n_cls = len(policy_data.LABELS)
    results, best_name, best_f1, best_model = {}, None, -1, None
    experiments = []

    def record(name, model, params, trainable, val_acc):
        nonlocal best_name, best_f1, best_model
        f1 = _f1(model, Xte, yte)
        results[name] = {"trainable_params": trainable, "val_accuracy": R(val_acc),
                         "unseen_accuracy": R(_acc(model, Xte, yte)), "unseen_macro_f1": R(f1)}
        experiments.append({"model": "policy clauses", "candidate": name, "params": params, "metric": "validation accuracy",
                            "cv_score": R(val_acc), "chosen": False})
        if val_acc > best_f1 - 1e-9 and (best_name is None or val_acc > results[best_name]["val_accuracy"]):
            best_name, best_f1, best_model = name, val_acc, model

    for r in (4, 8, 16):
        m = Classifier(copy.deepcopy(enc), n_cls)
        cfg = LoraConfig(r=r, lora_alpha=2 * r, lora_dropout=0.05, target_modules=["q_proj", "v_proj"],
                         modules_to_save=["classifier"])
        pm = get_peft_model(m, cfg)
        trainable = sum(p.numel() for p in pm.parameters() if p.requires_grad)
        va = _train_clf(pm, Xtr, ytr, Xva, yva, epochs=6, lr=3e-3)
        record(f"LoRA r={r}", pm, {"rank": r, "alpha": 2 * r, "dropout": 0.05, "targets": "q_proj,v_proj",
                                   "lr": 3e-3, "epochs": "≤6, best on dev style"}, trainable, va)
    m = Classifier(copy.deepcopy(enc), n_cls)
    va = _train_clf(m, Xtr, ytr, Xva, yva, epochs=6, lr=5e-4)
    record("full fine-tune", m, {"lr": 5e-4, "epochs": "≤6, best on dev style"}, sum(p.numel() for p in m.parameters()), va)
    m = Classifier(copy.deepcopy(enc), n_cls)
    for p in m.enc.parameters():
        p.requires_grad = False
    va = _train_clf(m, Xtr, ytr, Xva, yva, epochs=6, lr=3e-3)
    record("head only (frozen encoder)", m, {"lr": 3e-3, "epochs": "≤6, best on dev style"}, sum(p.numel() for p in m.classifier.parameters()), va)
    base = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
                         LogisticRegression(max_iter=3000, C=10)).fit(Xtr_t, ytr_l)
    results["TF-IDF + logistic regression (no neural net)"] = {
        "trainable_params": None, "val_accuracy": R(base.score(Xva_t, yva_l)),
        "unseen_accuracy": R(base.score(Xte_t, yte_l)), "unseen_macro_f1": R(f1_score(yte_l, base.predict(Xte_t), average="macro"))}
    import joblib

    joblib.dump(base, MODEL_DIR / "policy_tfidf.joblib")
    tfidf_dev = results["TF-IDF + logistic regression (no neural net)"]["val_accuracy"]
    lora_best = max((k for k in results if k.startswith("LoRA")), key=lambda k: results[k]["val_accuracy"])
    for e in experiments:
        e["chosen"] = e["candidate"] == best_name
    torch.save({"encoder": enc.state_dict(), "labels": policy_data.LABELS}, MODEL_DIR / "policy_encoder.pt")
    if best_name.startswith("LoRA") or results[lora_best]["val_accuracy"] >= results[best_name]["val_accuracy"] - 0.02:
        chosen = lora_best
    else:
        chosen = best_name
    # save the chosen classifier's full state (merged LoRA weights) for fast inference in the app
    for name, model in (("chosen", best_model),):
        mdl = best_model.merge_and_unload() if hasattr(best_model, "merge_and_unload") else best_model
        torch.save({"state": mdl.state_dict(), "labels": policy_data.LABELS, "name": best_name}, MODEL_DIR / "policy_clf.pt")
    deployed = "TF-IDF + logistic regression (no neural net)" if tfidf_dev > results[best_name]["val_accuracy"] else best_name
    (MODEL_DIR / "policy_deployed.txt").write_text(deployed)
    report = {"pretraining": pre, "train_sentences": len(Xtr_t), "unseen_test_sentences": len(Xte_t),
              "labels": policy_data.LABELS, "results": results, "best_neural_on_dev": best_name, "deployed": deployed,
              "validation": "a third, different writing style (dev) — never trained on, never the final test",
              "best_lora": lora_best, "seconds": round(time.time() - t0, 1)}
    (MODEL_DIR / "lora_report.json").write_text(json.dumps(report, indent=2))
    exp_path = MODEL_DIR / "experiments.json"
    old = json.loads(exp_path.read_text()) if exp_path.exists() else []
    old = [e for e in old if e["model"] != "policy clauses"] + experiments
    exp_path.write_text(json.dumps(old, indent=1))
    _ = chosen
    return report


# --------------------------------------------------------------------- inference
_clf = None


def classify_sentences(sents: list[str]) -> list[tuple[str, float]]:
    global _clf
    path = MODEL_DIR / "policy_clf.pt"
    if not path.exists() or not sents:
        return []
    if _clf is None:
        ck = torch.load(path, weights_only=False)
        m = Classifier(Encoder(), len(ck["labels"]))
        state = {k.replace("base_model.model.", "").replace("modules_to_save.default.", "").replace("original_module.", ""): v
                 for k, v in ck["state"].items()}
        m.load_state_dict(state, strict=False)
        m.eval()
        _clf = (m, ck["labels"])
    m, labels = _clf
    with torch.no_grad():
        p = m(input_ids=encode(sents)).softmax(-1)
    return [(labels[int(i)], float(c)) for c, i in zip(*p.max(-1))]


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
