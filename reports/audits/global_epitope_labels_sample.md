# Global epitope labels

First 10,000 rows per family; counts describe only the sample.

A positive label requires at least one positive source annotation for the exact original sequence.
Label zero means unlabeled in the input scope. A positive annotation does not establish binding across families, immunogenicity across organisms, or equivalent biological context.
Evidence counts are source rows and may include repeated observations.

## Original data

- Rows: 104,448
- Distinct original sequences: 64,209
- Rows labeled positive in their source family: 11,944
- Rows labeled negative in their source family: 92,504
- Exact sequences with both original labels: 1,918 (12,107 source rows)

## Global labels

- Positive distinct sequences: 4,003
- Unlabeled distinct sequences: 60,206
- Globally positive rows: 17,222
- Globally unlabeled rows: 87,226
- Rows with a changed label: 5,278 (5.05%)

## By family

| Family | Rows | Original + | Original − | Global + | Unlabeled | Converted | % of original − |
|---|---:|---:|---:|---:|---:|---:|---:|
| human/mhc-I/HLA-A | 10,000 | 773 | 9,227 | 1,321 | 8,679 | 548 | 5.94% |
| human/mhc-I/HLA-B | 10,000 | 1,148 | 8,852 | 2,072 | 7,928 | 924 | 10.44% |
| human/mhc-I/HLA-C | 10,000 | 349 | 9,651 | 1,092 | 8,908 | 743 | 7.70% |
| human/mhc-II/HLA-DP | 10,000 | 1,966 | 8,034 | 3,036 | 6,964 | 1,070 | 13.32% |
| human/mhc-II/HLA-DQ | 10,000 | 3,242 | 6,758 | 4,321 | 5,679 | 1,079 | 15.97% |
| human/mhc-II/HLA-DR | 10,000 | 2,413 | 7,587 | 3,202 | 6,798 | 789 | 10.40% |
| mouse/mhc-I/H2-D | 10,000 | 330 | 9,670 | 351 | 9,649 | 21 | 0.22% |
| mouse/mhc-I/H2-K | 10,000 | 240 | 9,760 | 290 | 9,710 | 50 | 0.51% |
| mouse/mhc-I/H2-L | 4,448 | 126 | 4,322 | 126 | 4,322 | 0 | 0.00% |
| mouse/mhc-II/H2-IA | 10,000 | 916 | 9,084 | 965 | 9,035 | 49 | 0.54% |
| mouse/mhc-II/H2-IE | 10,000 | 441 | 9,559 | 446 | 9,554 | 5 | 0.05% |

## Cross-family positive evidence

- Exactly 1 family: 3,411
- Exactly 2 families: 430
- Exactly 3 families: 138
- More than 3 families: 24

| Positive families | Distinct sequences |
|---:|---:|
| 0 | 60,206 |
| 1 | 3,411 |
| 2 | 430 |
| 3 | 138 |
| 4 | 23 |
| 5 | 1 |
| 6 | 0 |
| 7 | 0 |
| 8 | 0 |
| 9 | 0 |
| 10 | 0 |
| 11 | 0 |

## Validation

The audit checked family labels, original values, source and row identifiers, global evidence, and sequence totals against the original input scope. No embeddings, variants, scalers, or splits were generated or changed.
