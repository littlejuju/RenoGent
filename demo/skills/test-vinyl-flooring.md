# Decision profile: test-vinyl-flooring

## Priority rules (ordered, with weights)
1. **Durability/warranty length over price** (weight: high) — when comparing options within budget, reject shorter-warranty options even if cheaper. Evidenced by rejecting LF-201 "Nordic Oak" ($3.80/sqft, 15yr warranty) in favor of LF-202 "Honey Oak" ($4.20/sqft, 20yr warranty) — a $0.40/sqft premium paid for 5 extra years of warranty.
2. **Warm oak tone over lighter/sand oak tone** (weight: medium) — when durability is equal, prefer the warmer-toned option. Evidenced by choosing LF-202 "Honey Oak" over LF-210 "Sand Oak" (both AC4, both 20yr warranty) — and Honey Oak was also $0.30/sqft cheaper, so this preference wasn't tested against a price tradeoff yet.
3. **Price is a filter, not a driver** (weight: low) — the cheapest compliant option was explicitly passed over for better durability. Do not default to lowest price when a higher-durability option exists within budget.

## Hard constraints (never violate)
- Price ≤ $5.00/sqft installed
- Finish: matte
- Wear layer rating: AC4 minimum (household + pet/robot-vacuum traffic)
- Color family: oak (warm-toned preferred per Priority rule 2)

## Taste notes
- "Honey Oak" tone reads as the preferred warm-oak shade over "Sand Oak" (lighter/cooler) and "Nordic Oak" (likely grayer/cooler, also lowest durability).
- 20-year residential warranty is treated as a meaningfully better tier than 15-year — worth a modest price premium.

## Confidence: low
Why: Single decision instance logged (one requirements set, one 3-option choice). The ranking of "durability over price" and "warm tone over cool tone" is inferred from one comparison each — neither has been tested against a conflicting tradeoff (e.g., a much warmer-toned option that's also much less durable, or a very cheap high-durability option). Revisit and tighten weights once more decisions accumulate.