---
corpus: HDB renovation guidelines (citation-grade)
fetched: 2026-07-12
method: >
  All files were extracted verbatim from the official hdb.gov.sg pages. Page content
  is embedded in each page's __NEXT_DATA__ JSON payload (Next.js/Sitecore); accordion
  section HTML was extracted from that payload and converted to markdown with no
  paraphrasing. All files are primary-source (citation-grade). No secondary sources
  were needed.
---
# HDB Renovation Guidelines Corpus — Index

All rules text is verbatim from hdb.gov.sg (fetched 2026-07-12). Every file carries
`source_url` frontmatter. Files without `source_quality` are primary/citation-grade.

## Building works (all sections live on the single hub page)

Source URL for all files in this group:
`https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/renovation-guidelines/building-works`

| File | Topic |
|---|---|
| floor-finishes.md | Laying/replacement of floor finishes; 50mm total thickness limit; 13mm adhesive overlay limit; 120kg/m2 floor topping load limit; waterproofing screed/membrane (150mm upturn); 3-year bathroom floor finishes rule |
| walls.md | Erection of 63mm hollow block / 80mm glass block / gypsum partition walls; demolition and hacking of walls requires HDB prior approval; PE supervision for RC element demolition |
| wall-finishes.md | Wall finish replacement; 25mm total thickness limit; 13mm adhesive overlay limit; 3-year bathroom wall finishes rule |
| false-ceiling.md | False ceiling/cornice installation; 2.4m clearance height; 2.10m pelmet clearance; non-combustible materials; 6mm/40mm fastener limits; asbestos note for pre-1991 blocks |
| kitchen.md | Kitchen extension into service balcony/yard; dapoh slab/counter top rules; 50mm mortar-base thickness limit |
| refuse-chute-hopper.md | Alterations/replacement of refuse chute hopper |
| household-shelters.md | Household shelter (HS): no tampering with reinforced walls/floor slab/ceiling/steel door; 50mm max drill depth with non-metallic inserts; no adhesive floor finishes; SCDF guidelines; works not permitted in HS |
| door-and-gate.md | Replacement of main door, internal doors, front gate; fire-rated door requirements |
| sold-recess-area.md | Renovation of sold recess area |
| approved-rented-common-area.md | Renovation of approved rented common area outside flat |
| staircase.md | Staircase works (executive maisonettes) |
| bathroom-and-toilet.md | Bathroom/toilet kerb (100mm), enlargement after first 3 years (max 600mm / 0.6m2, dry area only), vent replacement (6mm wire-glass louvres) |
| awning.md | Installation of awning |
| others-building-works.md | Miscellaneous building works |

## Other primary pages

| File | Source URL | Topic |
|---|---|---|
| important-information-on-renovations.md | https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/important-information-on-renovations | DRC engagement requirement (Renovation Control Rules 2006); disallowed works; general T&C incl. permitted renovation hours (9:00am–6:00pm weekdays/Saturdays; restricted noisy works 9:00am–5:00pm weekdays only; no Sundays/PH); completion windows (3 months new blocks / 1 month existing / 2 weeks window works); max 3 consecutive days for demolition/removal works; DIY quiet hours 10.30pm–7.00am; debris rules ($2,000 skip tank fine); technical T&C incl. 3-year bathroom waterproofing restriction |
| window-works.md | https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/renovation-guidelines/window-works | Window installation/replacement/repair; BCA approved window contractor; grilles rules |
| electrical-works.md | https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/renovation-guidelines/electrical-works | EMA-licensed electrical worker; 30/40 amp loading; works requiring/not requiring permit |
| air-conditioner-installation-works.md | https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/renovation-guidelines/air-conditioner-installation-works | Air-con installation conditions; 30 amp vs 40 amp main switch rules; blocks completed on/after 1 Jan 1994 |
| water-sanitary-plumbing-and-gas-works.md | https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/renovation-guidelines/water-and-sanitary-plumbing-works-and-gas-works | PUB licensed plumber; sinks/basins, bath/shower, toilet pan, pipes; EMA licensed gas worker |
| application-for-a-renovation-permit.md | https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/application-for-a-renovation-permit | Permit application process; licensed persons table; Qualified Person (QP) works; floor plan purchase; debris removal charges |
| directory-of-renovation-contractors.md | https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/looking-for-renovation-contractors | Directory of Renovation Contractors (DRC); dispute resolution via CASE/SMC/Small Claims Tribunal |

## Coverage of requested special topics

- Renovation noise / permitted working hours → important-information-on-renovations.md ("Timings for carrying out renovations")
- Floor loading / floor raising thickness limits → floor-finishes.md (50mm screed+finish, 13mm adhesive overlay, 120kg/m2 topping load)
- Bathroom waterproofing 3-year restriction (new flats) → important-information-on-renovations.md (Technical T&C), floor-finishes.md, wall-finishes.md, bathroom-and-toilet.md
- DRC requirement → important-information-on-renovations.md, directory-of-renovation-contractors.md, application-for-a-renovation-permit.md
- Hacking of walls permit requirement → walls.md, important-information-on-renovations.md
- Household shelter no-hack/no-drill rules → household-shelters.md

## NOT CAPTURED

- `https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/renovation-guidelines/building-works/floor-finishes` — HTTP 404. Sub-category pages do not exist as separate URLs; all sub-category content lives in accordions on the building-works hub page and was captured from there instead.
- `https://www.hdb.gov.sg/managing-my-home/renovation-and-maintenance/renovation/renovation-guidelines` (parent hub) — fetched successfully but contains no rules text (pure navigation page); nothing to capture.
- Linked PDF attachments referenced inside the rules text were not fetched (rules cite them but the text itself is complete): "handheld power tools approved by HDB (PDF, 76KB)", drawing PDFs (e.g. "Drawing 3 (PDF, 20KB)"), and similar drawing references in walls/kitchen/awning sections.
- Precinct-specific guidelines for special precincts (e.g. DBSS) — behind MyHDB login per the page text; not publicly fetchable.
