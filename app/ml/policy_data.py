"""Synthetic but realistic store-policy sentences, labelled by clause type.

Two style families: TRAIN styles and UNSEEN styles (different phrasings, legalese, Indian e-commerce
wording, typos) so the final test measures generalisation, not memorisation.
"""
from __future__ import annotations

import numpy as np

LABELS = ["return_window", "replacement", "warranty", "exclusion", "condition", "shipping_cost", "refund_method", "other"]
NUM_WORDS = {7: "seven", 10: "ten", 14: "fourteen", 15: "fifteen", 30: "thirty", 60: "sixty", 90: "ninety"}

TRAIN = {
    "return_window": ["You may return most items within {n} days of {start} for a full refund.",
                      "Returns are accepted up to {n} days after {start}.",
                      "We offer a {n}-day return period from {start}.",
                      "Items can be returned within {n} days from the date of {start}.",
                      "If you change your mind, send it back within {n} days of {start}."],
    "replacement": ["Defective items qualify for a {n}-day replacement from {start}.",
                    "We will replace damaged products reported within {n} days of {start}.",
                    "Replacement is available for faulty items within {n} days.",
                    "If your item arrives defective we replace it free within {n} days of {start}."],
    "warranty": ["All {cat} carry a {w}-year limited warranty.", "This product comes with a {m}-month manufacturer warranty.",
                 "Warranty coverage lasts {w} year(s) from {start}.", "{cat} are covered by a {m}-month warranty against defects."],
    "exclusion": ["{cat} are non-returnable once opened.", "Final sale items cannot be returned.",
                  "Gift cards and downloadable software are not eligible for return.",
                  "Personalised products cannot be returned or exchanged.", "Clearance items are sold as is."],
    "condition": ["Items must be unused and in original packaging.", "Please include the receipt or proof of purchase.",
                  "Products must be returned with all tags attached.", "Returns must include all accessories and manuals."],
    "shipping_cost": ["Customer pays return shipping unless the item is defective.", "Return shipping is free.",
                      "A return shipping fee of {fee} will be deducted.", "We provide a prepaid return label."],
    "refund_method": ["Refunds are issued to the original payment method.", "Refunds are processed within {d} business days.",
                      "You will receive store credit instead of cash.", "Refunds go back to your card or PayPal account."],
    "other": ["Contact our support team for any questions.", "We reserve the right to update this policy.",
              "Thank you for shopping with us.", "Our stores are open from 9 am to 9 pm.",
              "Sign up to our newsletter for offers.", "Prices include all applicable taxes."],
}
UNSEEN = {
    "return_window": ["Easy {n} day returns, no questions asked.", "Not happy? You've got {n} days post {start} to send it back.",
                      "Return request must be raised within {n} days from {start}.",
                      "Purchaser may return goods within a period of {n} calendar days following {start}.",
                      "{n} days return policy applicable on this product."],
    "replacement": ["Damaged or defective product? Get a free replacement within {n} days.",
                    "Replacement only, within {n} days of {start}, for manufacturing defects.",
                    "In case of wrong item recieved, we will replace within {n} days."],
    "warranty": ["{w} year brand warranty.", "Manufacturer warranty of {m} months applicable.",
                 "The Seller warrants the product against defects for {w} years from the invoice date."],
    "exclusion": ["Innerwear, earrings and opened earphones are not returnable.", "No returns on sale items.",
                  "This item is non-refundable.", "Returns are not accepted for perishable goods."],
    "condition": ["Item should be in original condition with brand box.", "Return only with original invoice and tags intact.",
                  "Product must not be used, washed or damaged."],
    "shipping_cost": ["Free pickup available for returns.", "Return courier charges to be borne by customer.",
                      "Reverse pickup fee of {fee} applies."],
    "refund_method": ["Amount will be refunded to source account in {d}-{d2} working days.",
                      "Refund will be credited as wallet balance.", "Money back to original mode of payment."],
    "other": ["For bulk orders please email sales.", "Policy subject to change without notice.",
              "Delivery usually takes 3-5 days.", "Visit our help centre for more."],
}
DEV = {  # a third style family used ONLY to choose settings (never trained on, never the final test)
    "return_window": ["Changed your mind? Returns open for {n} days after {start}.", "We accept returns for {n} days.",
                      "Return eligibility: {n} days from {start}."],
    "replacement": ["Faulty on arrival? Replacement within {n} days.", "We swap defective units if reported in {n} days."],
    "warranty": ["Covered by {w} years warranty.", "Includes {m} months warranty from the brand."],
    "exclusion": ["Opened software is not returnable.", "Items marked final sale are excluded from returns."],
    "condition": ["Return the item unused with its box.", "Original receipt required for all returns."],
    "shipping_cost": ["You cover the cost of sending items back.", "Returns ship free of charge."],
    "refund_method": ["Refund goes to the card you paid with.", "Expect your refund in {d} days."],
    "other": ["Questions? Chat with us anytime.", "Opening hours vary on holidays."],
}
CATS = ["headphones", "speakers", "laptops", "phones", "watches", "earbuds", "chairs"]


def _fill(rng, t: str) -> str:
    n = int(rng.choice([7, 10, 14, 15, 30, 60, 90]))
    s = t.format(n=NUM_WORDS[n] if rng.random() < 0.25 and n in NUM_WORDS else n,
                 start=rng.choice(["delivery", "purchase", "receipt", "the order date"]),
                 cat=str(rng.choice(CATS)).capitalize(), w=int(rng.choice([1, 2, 3])), m=int(rng.choice([6, 12, 18, 24])),
                 fee=rng.choice(["$5", "₹99", "$7.50"]), d=int(rng.choice([3, 5, 7])), d2=int(rng.choice([8, 10])))
    if rng.random() < 0.15:
        s = s.upper() if rng.random() < 0.2 else s.lower()
    if rng.random() < 0.08 and len(s) > 10:  # typo
        i = int(rng.integers(1, len(s) - 1))
        s = s[:i] + s[i + 1:]
    return s


def make(style: str = "train", n_per_label: int = 300, seed: int = 0) -> tuple[list[str], list[int]]:
    rng = np.random.default_rng(seed)
    bank = {"train": TRAIN, "dev": DEV, "unseen": UNSEEN}[style]
    X, y = [], []
    for li, lab in enumerate(LABELS):
        for _ in range(n_per_label):
            X.append(_fill(rng, str(rng.choice(bank[lab]))))
            y.append(li)
    idx = rng.permutation(len(X))
    return [X[i] for i in idx], [y[i] for i in idx]


def augment(texts: list[str], labels: list[int], seed: int = 0, copies: int = 2) -> tuple[list[str], list[int]]:
    """Word dropout, word-order jitter and casing noise: pushes the model to rely on meaning-bearing words."""
    rng = np.random.default_rng(seed)
    X, y = list(texts), list(labels)
    for _ in range(copies):
        for t, l in zip(texts, labels):
            w = t.split()
            w = [x for x in w if rng.random() > 0.15] or w
            if len(w) > 3 and rng.random() < 0.3:
                i = int(rng.integers(0, len(w) - 1))
                w[i], w[i + 1] = w[i + 1], w[i]
            s2 = " ".join(w)
            X.append(s2.lower() if rng.random() < 0.5 else s2)
            y.append(l)
    return X, y


def pretrain_corpus(seed: int = 0, n: int = 6000) -> list[str]:
    """Unlabelled text for self-supervised pretraining: shopping/finance messages, transaction lines, policy-like text."""
    from .synth import INTENT_EXAMPLES, ITEMS
    rng = np.random.default_rng(seed + 1)
    texts = []
    for _ in range(n):
        r = rng.random()
        if r < 0.4:
            k = str(rng.choice(list(INTENT_EXAMPLES)))
            texts.append(str(rng.choice(INTENT_EXAMPLES[k])).format(item=rng.choice(ITEMS), amount="$500"))
        elif r < 0.75:
            lab = str(rng.choice(LABELS))
            texts.append(_fill(rng, str(rng.choice(TRAIN[lab]))))  # unlabelled: no labels are used in pretraining
        else:
            texts.append(f"{rng.choice(['FreshMart', 'TechKart', 'CloudHost', 'QuickCab'])} | "
                         f"{rng.choice(['order', 'monthly plan', 'invoice', 'refund'])} | {rng.integers(5, 900)}.00")
    return texts
