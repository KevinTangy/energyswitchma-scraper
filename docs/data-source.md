# Data source: EnergySwitch MA

## Site

- Consumer page: `https://energyswitchma.gov/#/compare/1/1/{zip}//`
- It's an AngularJS-style single-page app. The offer table is filled in by
  JavaScript, so WebFetch, curl and requests only see an empty shell.
  Scraping needs a real browser, which is why `scrape.py` uses Playwright.
- The first number in `/compare/{id}/1/` is the utility: `1` = National
  Grid, `2` = Eversource (per Kevin). The second `1` is probably the
  customer class (residential); not confirmed. `probe.py` loads both pages
  for a ZIP and reports which one lists competing offers; nothing about
  page 2's behavior has been observed directly yet.
- Towns served by a municipal light plant can't buy from competing
  suppliers (M.G.L. c. 164 §47A), so neither page should have offers.

## API endpoint

The page loads the offers from:

```
https://energyswitchma.gov/consumers/compare
```

The response is a JSON **list**, one object per offer. For ZIP 02148 on
2026-11-18 it held 42 offers.

`scrape.py` saves every JSON response the page loads into
`data/raw/<zip>/<date>.json.gz` (gzip-compressed, compact JSON), as a list of
`{"url": ..., "body": ...}`. View one with `zcat`.
`find_offers()` picks the entry whose URL contains `/consumers/compare`. As a
fallback, it uses any list of records that have `supplierName`.

Not tried yet: calling the endpoint directly without a browser. It might
need cookies, headers or a POST body that the app sends. That would be faster
and simpler than Playwright. To find out, inspect the request in browser
devtools.

## Fields used

| Field | Example | Notes |
|---|---|---|
| `supplierName` | `"National Grid"` | Goes in the CSV `supplier` column |
| `supplierId` | `214` | Numeric. Do NOT use as the supplier (an early bug) |
| `pricePerUnit` | `"17.185 ¢/kWh\|16.077 ¢/kWh"` | `\|`-separated for basic service; one value for other offers |
| `fixedPrice` | | Fallback if `pricePerUnit` is empty |
| `contractTerm` | `"Aug '26 through Jan '27 \|Feb '27 through Jul '27 "` | `\|`-separated to match `pricePerUnit`. Can have stray spaces or start with a space (`" through Dec '27"`), so always `.strip()` |
| `isDistributionCompany` | `true` | Marks the utility's basic service record (`rowType: "DistributionCompany"`) |
| `earlyTerminationDetail` | `"Cancellation fee: $150.00"` / `null` | `null` is shown as "No cancellation fee" |
| `enrollmentFee` | `null` | Added to fees when present |
| `pricePerMonth` | `null` | Monthly charge; added to fees when present |

## Other notable fields (not used yet)

- `isManualRemoval`: `true` on 1 of 42 Malden offers (Clearview Energy,
  9 months, 18.49¢). It probably means the offer is hidden on the site. It's
  currently KEPT in the CSV, and Kevin hasn't decided whether to filter it out.
- `isMunicipalAggregationDefault`, `municipalAggregationTown`: city-run
  electricity programs. In Malden, "Malden Community Electricity" has 3
  products (13.345¢ at 0% renewable, 13.758¢ at 79% renewable and the default
  plan, 14.696¢ at 100% renewable), all for a term ending Dec '27. The 13.345¢
  product is currently the "cheapest offer" in Malden.
- `renewableEnergyProductPercentage`: how a supplier's several products
  differ. Since the product and renewable columns were removed, one supplier
  can appear on several CSV rows with different prices.
- `contractTermEndDate`, `automaticRenewal*`, `introductoryPrice`,
  `isNewCustomerOnly`, `estimatedCost`, `rowNum`, `sortOrder`,
  `supplierProductId`, `productWebsiteUrl`, `phone`.

## Sample capture

`data/raw/02148/2026-11-18.json.gz` (about 7 KB compressed, 112 KB as
originally saved) is the reference fixture used
to build and test the parsing.
