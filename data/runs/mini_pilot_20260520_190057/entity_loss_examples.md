# Entity Loss Examples (1x vs 5x)

Scope: compares repaired outputs at `1x` vs `5x` for each patient.
Wording is descriptive only (pilot-scale; N=3).

## patient_01

### `conditions` (changed: yes)

**Missing at 5x (present at 1x):**
- Asthma
- Seasonal allergic rhinitis

**New at 5x (not present at 1x):**
- Asthma exacerbation

### `medications` (changed: no)

**Missing at 5x (present at 1x):**
- (none)

**New at 5x (not present at 1x):**
- (none)

### `observations` (changed: yes)

**Missing at 5x (present at 1x):**
- {'name': 'SpO2', 'value': '94%'}

**New at 5x (not present at 1x):**
- {'name': 'SpO2', 'value': '94%', 'unit': 'on room air'}

### `procedures` (changed: yes)

**Missing at 5x (present at 1x):**
- Nebulized bronchodilator treatment

**New at 5x (not present at 1x):**
- {'name': 'Nebulized bronchodilator treatment', 'location': 'ED'}

## patient_02

### `conditions` (changed: no)

**Missing at 5x (present at 1x):**
- (none)

**New at 5x (not present at 1x):**
- (none)

### `medications` (changed: no)

**Missing at 5x (present at 1x):**
- (none)

**New at 5x (not present at 1x):**
- (none)

### `observations` (changed: yes)

**Missing at 5x (present at 1x):**
- Temp 38.1 C
- WBC 14.2 K/uL

**New at 5x (not present at 1x):**
- {'value': '14.2', 'unit': 'K/uL'}
- {'value': '38.1 C', 'unit': 'C'}

### `procedures` (changed: no)

**Missing at 5x (present at 1x):**
- (none)

**New at 5x (not present at 1x):**
- (none)

## patient_03

### `conditions` (changed: no)

**Missing at 5x (present at 1x):**
- (none)

**New at 5x (not present at 1x):**
- (none)

### `medications` (changed: no)

**Missing at 5x (present at 1x):**
- (none)

**New at 5x (not present at 1x):**
- (none)

### `observations` (changed: no)

**Missing at 5x (present at 1x):**
- (none)

**New at 5x (not present at 1x):**
- (none)

### `procedures` (changed: no)

**Missing at 5x (present at 1x):**
- (none)

**New at 5x (not present at 1x):**
- (none)

