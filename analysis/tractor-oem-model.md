# Tractor / OEM Motor Distribution Model
### Working model — grounded in Part 1 (Box 4A) and Part 2 (Table 1/4/5) data
### CORRECTED — Section 9 payment-architecture point was a non-issue; struck below.

**Context:** Bharat Bima's tractor model economics were already planned around a ~5% commission assumption — close to the new Box 4A cap for IDE new-vehicle OD/PA/LL (5%), well below current market average (Table 1: motor new business avg 26%, range 13-50% per Table 4).

**Routing decision:** go via OEM/manufacturer tie-up, not individual dealer or NBFC financing route. Rationale: individual tractor dealers lose their incentive to actively push insurance once their own take compresses to 5% — same "not worth the operational hassle" dynamic already identified for NBFCs and their own master policies (see affinity-model-unbundling-thesis.md, Opportunity 1). Manufacturer-route gives scale across a whole dealer network in one relationship instead of one-off dealer deals, which matters more precisely because per-unit economics are thin.

**Open risk — will 5% actually be retained?**
- Box 4A's 5% (IDE, new vehicle OD/PA/LL) is a **maximum cap, not a guaranteed floor.**
- Motor already carries the **highest average commission of any general insurance line today** (Table 1: 26% new business avg, vs Health Retail 24%, Health Group 15%, Property 14%) — meaning it's the line insurers have the most room to cut and the most pressure to cut, especially insurers furthest along the EoM glide path (small/niche general insurers ~40% EoM must nearly halve their expense base in 5 years to reach the 20% target; large insurers ~23-30% have comparatively more room).
- **Practical implication:** insurer selection is a real lever here, not a footnote. Large insurers with more EoM glide-path headroom are more likely to actually pay the full 5%; small/niche insurers under the most pressure are the ones most likely to push motor commission below the printed cap, since it's their fattest current line to cut.

**The "nobody sells motor at 5%" problem — same structural answer as the NBFC Layer 1 case:**
- At 5% commission, no human sales push is economically justified — this is a real, correct objection, not solved by wishful thinking.
- Solution: don't build a human sales model for this. Embed distribution at the point of an already-happening transaction — tractor delivery/registration through the OEM's dealer network — automatic, API-driven, using the same Section 9 verified-connect rails (OTP/Aadhaar) that are mandatory regardless. Near-zero marginal cost per policy makes 5% (or even somewhat below) workable at volume; human-sales-cost-per-policy never would have.

**~~Payment architecture constraint~~ — CORRECTED, non-issue:** originally flagged para 126's direct customer→insurer money flow as a day-one architecture decision needed for this model. Corrected: **Bharat Bima does not collect or pool premium in any existing model** — this is already standard practice, not a new constraint requiring design work. No action needed here.

**Pattern recognition, worth naming explicitly:** this is structurally the same insight as the NBFC Layer 1 model (see affinity-model-unbundling-thesis.md) — wherever commission compression kills human-sales economics, the answer is embedded/API distribution at the point of an already-happening transaction (loan disbursal, vehicle delivery), not a sales team. If this pattern holds across two independently-arrived-at verticals, it may be **the actual core operating model thesis for Bharat Bima broadly**, not a one-off fix per vertical — worth testing against any future vertical the same way.

**Open questions:**
- Does Bharat Bima have or can it build the OEM-level API/integration relationship needed, or is this a multi-year build like the NBFC LOS-integration question?
- Which tractor OEMs are realistic partners given the founding team's network?
- How does insurer selection get operationalized in practice — is there a way to negotiate/prioritize insurer partners by EoM headroom before committing to a tractor-line insurer panel?
- Rural Category-II bonus (+20% on the cap) likely applies to most tractor business — does this materially change the "will we retain 5%" risk calculus (effective ~6% cap headroom) or is it a rounding error against the bigger insurer-selection risk?
- Suitability/mis-selling compliance build (Section 11 — see compliance-cost-benefit-ledger.md) applies to this model same as NBFC Layer 1: high-volume, low-touch transactions are exactly the profile PIR seller-tagging is designed to catch. Needs the same system + compliant-people build being tracked there.

**Status:** promising, grounded in real data. The "embedded/API distribution at point of transaction" pattern is now confirmed across two verticals (NBFC lending, tractor/OEM) — worth treating as a standing operating principle, not just a per-vertical fix.
