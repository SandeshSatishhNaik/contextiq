# ContextIQ: submission pack (start here)

Everything needed to submit **ContextIQ** to the PayPal AI Hackathon on Devpost. **Deadline: Nov 12, 2026, 12:00 pm PT.** After that nothing can be changed. Keep the demo and the sandbox login working until **Dec 21**.

## What's in this zip
| Folder | What it is |
|---|---|
| `01_devpost_text/SUBMISSION_KIT.md` | **The text to paste:** tagline, the full story in Devpost's sections, Built With tags, the Tools section, gallery captions, requirements checklist |
| `02_gallery/` | 10 images, numbered in upload order (captions are in the kit) |
| `03_video/ContextIQ_demo.mp4` | The demo video (2:54). **Already on YouTube, public:** https://youtu.be/cGJgYqDmotg |
| `04_source_code/contextiq-source.zip` | A snapshot of the full source, the same as the public repo |
| `05_supporting/` | Model and agent health report, and the demo shot list |

## Links (all live)
- **Hosted demo, guided judge tour:** https://contextiq-0ihy.onrender.com/?demo=1
- **Public repo (Apache-2.0):** https://github.com/SandeshSatishhNaik/contextiq
- **Demo video (public, 2:54):** https://youtu.be/cGJgYqDmotg
- **Team:** Avoflare

## Fill in the Devpost form (about 15 minutes)
1. **Project name:** ContextIQ.
2. **Elevator pitch / tagline:** copy the "Use this one" tagline from the kit.
3. **About the project (story):** paste everything from "### Inspiration" through "### What's next for ContextIQ".
4. **Built with:** add the tags from the kit's "Built with" section.
5. **Tools field** (which AI models and services, and how they're used): paste the Tools table and the model results under it.
6. **Try it out links:** the hosted demo URL and the repo URL.
7. **Video demo link:** https://youtu.be/cGJgYqDmotg
8. **Image gallery:** upload `02_gallery/01-cover.jpg` through `10-how-it-works.jpg` in order. Make `01-cover.jpg` the thumbnail.
9. **Test credentials / instructions for judges:** use the block below, once the sandbox buyer exists (next section).
10. **Sponsor prizes:** tick **Render**; the hosted demo runs on Render.
11. **Team:** make sure every Avoflare teammate has **accepted** their Devpost invite before you submit.
12. Check the preview, then **Submit**.

## Before submitting: the judges' sandbox buyer (about 1 minute)
Use the **existing sandbox buyer** the demo already uses:

- **Email:** `sb-hfln853812063@personal.example.com`. The app pre-fills it in the PayPal popup, and the real sandbox dispute ran on this account.
- **Password:** look it up at https://developer.paypal.com → **Testing Tools → Sandbox Accounts** → this account → **⋮ → View/Edit account**.
  - Judges will see it, so it must not be a password you use anywhere real.
  - If you chose it yourself and it matches a real password, change it on the same screen first.
- **Quick check:** on the hosted demo, go to Cart → Buy → PayPal button, log in with it, and approve.

Then paste this into Devpost's test-credentials field, with the password filled in:

```
Hosted demo (guided tour): https://contextiq-0ihy.onrender.com/?demo=1
PayPal SANDBOX buyer (test money only, no real payments):
  email:    sb-hfln853812063@personal.example.com
  password: <sandbox buyer password>
How to test: follow the 5-step tour bar at the top. Use the Buyer/Seller switch in the top bar.
Step 3 (dispute): log in with the same sandbox buyer at https://www.sandbox.paypal.com,
open the payment, Report a problem > Item not received. The dispute reaches ContextIQ in a few minutes.
The site is on a free host: the first load after a quiet spell can take about a minute.
```

(If you'd rather not share this account, create a fresh **Personal (buyer)** account on the same Sandbox Accounts page and use that instead.)

Don't put this password in the GitHub repo or the README.

## Also before submitting: Chrome's "Dangerous site" warning
Google Safe Browsing flagged the new demo URL, most likely because of PayPal branding on a brand-new subdomain. The phishing-like signals are removed and the verification file is live; a review just needs requesting.
1. https://search.google.com/search-console → **Add property** → **URL prefix** → `https://contextiq-0ihy.onrender.com/` → method **HTML file** → **Verify**. The file `google2e90fd689cc95140.html` is already served, so it should verify straight away.
2. **Security & Manual Actions → Security issues → Request review.** Explain: "Hackathon demo on the PayPal sandbox, not affiliated with PayPal, never asks for PayPal credentials (approval happens on paypal.com). Removed the /paypal/return URL pattern."
3. Reviews usually take one to three days, so it should clear before judging ends.

## Requirements check (Devpost rules)
| Requirement | Status |
|---|---|
| Built with PayPal + AI | ✅ |
| Text description | ✅ in the kit |
| Functional demo (hosted URL and/or run instructions) | ✅ both |
| Tools: models and services, and how they're used | ✅ in the kit |
| Public repo, with all source and run instructions | ✅ |
| Open-source license in the repo's About section | ✅ Apache-2.0 |
| Video under 3 minutes, public on YouTube, working project | ✅ 2:54, public |
| No unlicensed trademarks or music | ✅ no music; only the sponsor's own sandbox UI |
| Test credentials for judges | ⬜ paste the existing sandbox buyer's login (above) |

## After submitting
- Change nothing until Dec 21: don't push to the repo, and don't redeploy the demo.
- Keep the PayPal sandbox app and the Render service running.
- Rotate the PayPal sandbox secret and the Groq key when convenient, then update `.env` and Render's Environment tab. (They appeared in a chat log during development.)
