# Tractor / OEM Motor Distribution Model
### Grounded in Part 1 (Box 4A) and Part 2 (commission benchmark data)

**Context:** Bharat Bima's tractor model economics are planned around a ~5% commission assumption — close to the new Box 4A cap for IDE new-vehicle OD/PA/LL (5%), well below the current market average (26% new-business average, 13-50% range across insurers).

**Routing decision:** go via OEM/manufacturer tie-up, not individual dealer or NBFC financing route. Individual tractor dealers lose their incentive to actively push insurance once their own take compresses to 5% — the same dynamic already identified for NBFCs and their own master policies (see affinity-model-unbundling-thesis.md, Opportunity 1). The manufacturer route gives scale across a whole dealer network in one relationship instead of one-off dealer deals, which matters more precisely because per-unit economics are thin.

**Will 5% actually be retained?**
- Box 4A's 5% (IDE, new vehicle OD/PA/LL) is a maximum cap, not a guaranteed floor.
- Motor already carries the highest average commission of any general insurance line today (26% new-business average, vs Health Retail 24%, Health Group 15%, Property 14%) — meaning it's the line insurers have the most room to cut and the most pressure to cut, especially insurers furthest along the EoM glide path. Part 2's insurer-level expense-ratio data (see part2-full-data-analysis.md) confirms small/niche general insurers running 35-43%+ expense ratios today against a 20% five-year target, versus large insurers already near or below it.
- **Practical implication:** insurer selection is a real lever, not a footnote. Large insurers with more EoM glide-path headroom are more likely to actually pay the full 5%; small/niche insurers under the most pressure are the ones most likely to push motor commission below the printed cap, since it's their fastest lever to hit the glide path.

**The "nobody sells motor at 5%" problem — the same structural answer as the NBFC Layer 1 case:**
At 5% commission, no human sales push is economically justified. The solution is not to build a human sales model for this at all: embed distribution at the point of an already-happening transaction — tractor delivery/registration through the OEM's dealer network — automatic, API-driven, using the same Section 9 verified-connect rails (OTP/Aadhaar) that are mandatory regardless. Near-zero marginal cost per policy makes 5% (or even somewhat below) workable at volume; a human-sales-cost-per-policy model never would be.

Bharat Bima does not collect or pool premium in any existing or planned model, so Section 9's direct customer-to-insurer money-flow requirement (para 126) is a non-issue here — no architecture change needed.

**Pattern:** this is structurally the same insight as the NBFC Layer 1 model (see affinity-model-unbundling-thesis.md) — wherever commission compression kills human-sales economics, the answer is embedded/API distribution at the point of an already-happening transaction (loan disbursal, vehicle delivery), not a sales team. This pattern, confirmed across two independently-developed verticals, is worth treating as a standing operating principle for Bharat Bima broadly, not a one-off fix per vertical.

**Open questions:**
- Whether Bharat Bima has, or can build, the OEM-level API/integration relationship this model needs.
- Which tractor OEMs are realistic partners given the founding team's network.
- How insurer selection gets operationalized in practice — negotiating/prioritizing insurer partners by EoM headroom before committing to a tractor-line insurer panel.
- Whether the rural Category-II bonus (+20% on the cap, likely applicable to most tractor business) materially changes the "will we retain 5%" risk calculus (effective ~6% cap headroom), or is a rounding error against the bigger insurer-selection risk.
- The suitability/mis-selling compliance build (Section 11 — see compliance-cost-benefit-ledger.md) applies to this model the same as NBFC Layer 1: high-volume, low-touch transactions are exactly the profile PIR seller-tagging is designed to catch, and need the same system-plus-compliant-people build.

**Status:** grounded in real data, with the "embedded/API distribution at point of transaction" pattern now confirmed across two verticals (NBFC lending, tractor/OEM) — treated as a standing operating principle for the business, not just a per-vertical fix.
