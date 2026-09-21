# The Smol Model Company of New Haven — Brand Identity & Design Specification

**Document reference:** SMCo-SPEC-REV-2026.09
**Supervisory authority:** Model Systems Laboratory / Division of Constrained Computational Systems
**Station:** Crown & College Precinct, New Haven, Connecticut

This document is the design specification for the project's public identity: naming,
color, typography, iconography, hardware and terminal presentation, and publishing
conventions. It is the source design brief for anyone building or reviewing visual
work for the public site (`site/`) or physical/print artifacts, and it should be
shared as-is with a design collaborator before new visual work starts. It records
intended design direction, not a shipped implementation; align new site or asset
work with `site/AGENTS.md` and check for drift against what is actually deployed
before treating any detail here as current fact.

---

## 1. Executive brand architecture & nomenclature

### 1.1 Organizational hierarchy

The institution operates across three distinct formal levels of nomenclature:
1. **Parent scientific body:** `THE SMOL MODEL COMPANY OF NEW HAVEN`
2. **Operational research bench:** `MODEL SYSTEMS LABORATORY`
3. **Engineering & infrastructure directorate:** `DIVISION OF CONSTRAINED COMPUTATIONAL SYSTEMS`

### 1.2 Approved public & technical naming

* **Full formal name:** *The Smol Model Company of New Haven* (used on monographs, building signage, and legal documentation).
* **Standard public name:** *The Smol Model Company*
* **Institutional shorthand / monogram:** `SMCo. / NHV` (typeset with full-height `SM` and raised/small-cap `Co.` with amber period).
* **Software / runtime notation:** `[-]` or `[▪]`
* **Repository / git namespace:** `smol-model-co` / `smc-research`
* **CLI prompt syntax:** `smc:nhv/lab4>` or `smc:nhv/needle-04>`

### 1.3 Institutional mandate & credo

* **Primary research directive:**
  > "The Smol Model Company of New Haven is an independent research project studying how much useful reasoning, adaptation, and generalization can be extracted from small models under practical compute constraints."
* **Core institutional motto:** "Research Systems for a More Constrained World."
* **Secondary working principle:** "Small models. Real problems."
* **The empirical axiom:** "Measured Evidence > Benchmark Claims." If there is a number on our publications or surfaces, somebody measured it on physical silicon.
* **Understated legal disclaimer:** `NOT A COMPANY™.` (preserved in technical footers to uphold the dry institutional humor).

---

## 2. The core compression glyph (symbol architecture)

The mark is not a decorative logo; it is a geometric metrology diagram representing
**high-density capability compressed into a rigid physical envelope**.

```
       240 PT BOUNDARY ALLOCATION
┌───────────────────────────────────────┐ ──
│                   │                   │  ▲
│                   │                   │  │
│                   │                   │  │
│         ┌───────────────────┐         │  │
│         │   4x4 SUB-GRID    │         │  │ 240 PT
│─────────│     SMOL CORE     │─────────│  │ ALLOCATION
│         │    [60x60 PT]     │         │  │
│         └───────────────────┘         │  │
│                   │                   │  │
│                   │                   │  │
│                   │                   │  ▼
└───────────────────────────────────────┘ ──
  4:1 Linear Reduction  /  16:1 Surface Area Compression
```

### 2.1 Mathematical construction

* **Linear proportion:** 4:1 reduction (240 pt envelope to 60 pt inner core).
* **Surface area compression:** exactly 16:1 (core area = 1/16 of envelope area).
* **Envelope stroke weight:** 10 pt solid black line on standard master grid.
* **Center registration:** hairline grid registration crosses passing through the exact centroid of the square.

### 2.2 Optical sizing tiers (size-specific manifestations)

1. **Monumental / display (≥ 96 pt):**
   * Outer boundary frame with a visible internal 4×4 sub-matrix grid printed inside the cadmium ochre core.
   * *Usage:* monograph title covers, architectural signage, presentation placards.
2. **Document scale (16 pt – 32 pt):**
   * Sub-grid collapses into a solid, razor-sharp dense ochre square within the black frame.
   * *Usage:* specimen cards, repo headers, research note folios, asset stickers.
3. **Runtime / inline glyphs (6 pt – 12 pt):**
   * Bracketed terminal character: `[-]` or Unicode dense block `[▪]`.
   * *Usage:* CLI shells, table columns, code comments, status registers.

---

## 3. Color standards & metrology

The palette synthesizes **Bell System 1968 industrial telecommunications** with the
**Long Island Sound coastal laboratory** ethos. It deliberately avoids modern AI
startup tropes (neon orange, purple-blue SaaS gradients, dark-mode chrome).

### 3.1 Primary institutional palette

| Swatch name | Hex code | Material & historical reference | Functional role |
| :--- | :--- | :--- | :--- |
| Manila Paper Cream | `#EFE9DC` | Aged Western Electric document folder | Primary background paper stock |
| High-Contrast Cream | `#F7F3EA` | Bleached card stock / insert sheets | Card interiors, table row alternating tint |
| Muted Ledger | `#E2D9C8` | Heavy ledger borders & unbleached rules | Secondary containers and dividers |
| Carbon Ribbon Black | `#18191A` | Typewriter carbon ribbon ink | Primary body copy, headers, boundary frame |
| Telco Instrument Gray | `#485258` | Western Electric 19-inch rack enclosures | Structural containers, primary badges, buttons |
| Chassis Slate | `#657077` | Technical metrology rules & wiring slate | Metadata, dimension markers, table labels |
| Cadmium Linseed Ochre | `#C47A1B` | Lead/linseed warning enamel, amber lamps | Primary signal accent (status, core glyph) |
| Ochre Dim / Border | `#9E5D0E` | Engraved matrix rules inside ochre core | Inner matrix gridlines and hover borders |
| Ochre Tint / Wash | `#F8F1E4` | Diluted linseed wash | Highlighted table cells and callout boxes |

### 3.2 Secondary classification palette (research taxonomy)

| Swatch name | Hex code | Classification role | Applied condition |
| :--- | :--- | :--- | :--- |
| Marine Lichen Pine | `#364B3E` | Verified standards & controlled results | Stable, reproduced findings (TR-001) |
| Weathered Buoy Rust | `#A4492E` | Negative results & exploratory probes | Failed experiments, quantization limits |
| Metrology Steel Blue | `#4B6375` | Cross-platform telemetry & ports | Architecture bridges, ARM NEON runs |
| CRT Obsidian Glass | `#0F1214` | Command-line runtime shells | Terminal backgrounds, serial data plates |

---

## 4. Typographic system (the three-voice engine)

The organization communicates through three disciplined typographic voices working
in strict harmony.

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. INSTITUTIONAL SANS : IBM Plex Sans (or Neue Haas Grotesk)           │
│    "THE SMOL MODEL COMPANY OF NEW HAVEN — MODEL SYSTEMS LABORATORY"    │
│    Role: Institutional authority, wayfinding, mastheads, hardware plates│
├────────────────────────────────────────────────────────────────────────┤
│ 2. SCHOLARLY SERIF    : Newsreader (or Fournier / Century Expanded)    │
│    "Deterministic Semantic Routing on Legacy ARMv7 Hardware..."        │
│    Role: Academic gravity, research paper titles, abstracts, monographs│
├────────────────────────────────────────────────────────────────────────┤
│ 3. APPARATUS MONO     : IBM Plex Mono (or Letter Gothic / OCR-B)       │
│    "SMC-PRG-01 | LATENCY: 0.88ms | RSS: 38.4MB | ZERO FAULTS"          │
│    Role: Precision metrology, specimen cards, CLI runtime, registers   │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Typographic hierarchy rules

* **Document headers:** sans-serif, all-caps, letterspaced (tight tracking to wider tracking on subtitles).
* **Scientific abstracts:** serif, 13–15pt, italicized subheaders, bordered with a thick Telco Gray (`#485258`) left vertical rule.
* **Metadata key-value pairs:** monospace, strictly uppercase keys (`TARGET SILICON:`, `MEASURED METRIC:`), right-aligned or tabulated values.

---

## 5. Active research programs & specimen system

Models and research programs are catalogued as distinct **computational specimens**
evaluated under severe physical constraints.

### 5.1 Program catalogue registry

| Program ID | Codename | Central scientific inquiry | Target silicon | Status / claim tier |
| :--- | :--- | :--- | :--- | :--- |
| SMC-PRG-01 | Needle Router | Deterministic 4-way semantic gating without bus stalls or memory paging? | Sony PSTV (ARM Cortex-A9 @ 444MHz, 512MB RAM) | Controlled result (0.88ms latency, 0 page faults) |
| SMC-PRG-02 | Reusable Skills | Can factorized procedural skill blocks improve out-of-distribution holdouts? | RTX 3080 Ampere station (10GB VRAM) | Development signal (+18.4% compositional gain) |
| SMC-PRG-03 | Recurrent Comp. | Can repeated passes over tied weights replace deep feedforward layers? | ARMv7 / generic ARMv8 Linux | Active benchmark (73% param reduction, testing drift) |
| SMC-PRG-04 | Temporary Adapt. | Can a frozen model assimilate transient rules in an isolated scratchpad? | Embedded Linux node / PSTV | Exploratory probe (32KB bounded buffer, zero drift) |

Program IDs and status tiers here are illustrative naming/claim conventions for the
design system, not a substitute for the actual tracked experiments in
[research-design.md](../research-design.md), [results.md](../results.md), and
[research-map.md](../research-map.md). Any specimen card built from this spec must
cite the live experiment record, not this table, for real status and numbers.

### 5.2 Specimen card schematic syntax

Every specimen card must display its routing topology using fixed ASCII logic:

```text
[QUERY STREAM] ──► [GATE: INT8] ─┬─► [EXPERT-A: REASONING] (ACTIVE)
                                 ├─► [EXPERT-B: FORMAT/JSON] (IDLE)
                                 └─► [EXPERT-C: ESCALATE]   (IDLE)
[RETURN BUS] ◄── [VERIFIER: ▪] ◄─┘
```

---

## 6. Industrial hardware & physical instrument design

The physical computing appliances are designed as industrial laboratory equipment
rather than consumer gadgets.

```
┌──────────────────────────────────────────────────────────────────────────┐
│(·)                                                                    (·)│
│   ┌───────────────────────────────────────────────┐ ┌────────────────┐   │
│   │ THE SMOL MODEL COMPANY OF NEW HAVEN           │ │SYSTEM TELEMETRY│   │
│   │ LOCAL INFERENCE PROCESSOR — ARM ENCLOSURE     │ │ARM CORE: 444MHz│   │
│   │ PART NO: SM-PSTV-04A   SERIAL: 2026-0819-NH   │ │GATE: READY (●) │   │
│   │ MEMORY FLOOR: 512 MB RIGID LPDDR2             │ │SWAP: 0%        │   │
│   │ CALIBRATION: CERTIFIED CONDENSED              │ └────────────────┘   │
│   └───────────────────────────────────────────────┘ ┌────────────────┐   │
│                                                     │[PORT A] [PORT B]│  │
│               [=== CALIBRATION TAMPER SEAL ===]     └────────────────┘   │
│(·)            VOID IF ALLOCATION REG OVERWRITTEN                      (·)│
└──────────────────────────────────────────────────────────────────────────┘
```

### 6.1 Mechanical specifications

* **Chassis substrate:** bead-blasted natural anodized 6061 aluminum or cold-rolled instrument gray steel plate.
* **Fasteners:** four corner slotted-head pan screws with split-lock washers.
* **Data plate:** 0.8mm photo-etched black-oxide aluminum serial plate attached via four blind dome rivets.
* **Nomenclature:** DIN 1451 Mittelschrift / IBM Plex Mono silkscreening: `PORT A (BUS I/O)`, `PORT B (PROBE)`.
* **Telemetry indicators:** flush-mount 3mm diffused amber LEDs (`#C47A1B`) with warm glow profiles.
* **Tamper seal:** destructible eggshell paper seal spanning the chassis seam:
  * "CALIBRATION TAMPER SEAL — THE SMOL MODEL COMPANY · VOID IF BROKEN OR ALLOCATION REGISTER OVERWRITTEN."
  * Checkerboard border printed in Linseed Ochre.

### 6.2 Laboratory hardware fleet

1. **Flagship proof bench:** Sony PlayStation TV (PSTV) — quad-core ARM Cortex-A9 MPCore @ 444MHz, 512MB shared LPDDR2. Unpaged, rigid physical memory constraint.
2. **Synthesis & distillation node:** RTX 3080 workstation (10GB GDDR6X, GA102 Ampere) + Ryzen 9 5900X (64GB RAM).
3. **Cross-architecture target:** embedded ARMv8 Linux nodes (Cortex-A53 edge processors).

Treat hardware identity and performance claims in sections 5 and 6 as design
placeholders until they match a manifested, reviewed run — see
[compute.md](../compute.md) for the actual hardware policy and inventory.

---

## 7. Software & terminal runtime: the CSR console

The command-line interface is the primary operational surface for researchers.

### 7.1 Interface specification

* **Terminal standard:** VT100 / ANSI 80×24 monospaced console.
* **Background:** obsidian CRT glass (`#0A0C0E`).
* **Foreground:** unbleached paper white (`#EFE9DC` / `#D4D8DC`).
* **Active status / prompt:** linseed ochre (`#C47A1B`).

### 7.2 Telemetry MOTD output

```text
┌─┐
│▪│  THE SMOL MODEL COMPANY OF NEW HAVEN
└─┘  Model Systems Laboratory :: Constrained Systems Runtime (CSR)
════════════════════════════════════════════════════════════════════════════════
MANDATE              : "Research Systems for a More Constrained World."
ACTIVE PHYSICAL BENCH: Sony PSTV (ARMv7 @ 444MHz, 512MB RAM)
VERIFIED BENCHMARK   : SMC-PRG-01 Needle Router [0.88ms / 0 Page Faults]
STATUS               : ONLINE [Evaluation Contract: Strict]
════════════════════════════════════════════════════════════════════════════════
```

### 7.3 Standard command suite

* `evidence` — prints physical silicon latency, resident set memory (RSS), and fault counters.
* `programs` — lists active controlled research tracks and their current hardware targets.
* `hardware` — dumps specifications for active laboratory silicon testbeds.
* `methods` — prints the 8-point New Haven Evaluation Contract.
* `questions` — summarizes the 6 foundational inquiries on constrained reasoning.
* `staff` — displays the mid-century laboratory staff and appointment registry.

---

## 8. Publishing standards & the New Haven Evaluation Contract

Every technical report, monograph, and benchmark follows an explicit scientific
pact. This mirrors, in design-system form, the same reproducibility discipline
already required in [AGENTS.md](../../AGENTS.md) and
[evaluation.md](../evaluation.md).

```
                  THE NEW HAVEN EVALUATION CONTRACT
┌──────────────────────────────┬──────────────────────────────┐
│ 01. FIXED EVAL CONTRACTS     │ 02. STRICT DATA ISOLATION    │
│ Pre-committed, frozen schemas│ Train / Dev / Final isolated │
├──────────────────────────────┼──────────────────────────────┤
│ 03. MANIFEST REPRODUCIBILITY │ 04. PHYSICAL MEASUREMENT     │
│ Git hash + seeds + compiler  │ Real wall-clock ms & RSS memory│
├──────────────────────────────┼──────────────────────────────┤
│ 05. FAILURE PRESERVATION     │ 06. EXPLICIT CLAIM LEVELS    │
│ Dead ends logged with dignity│ Signal vs Controlled Result  │
├──────────────────────────────┼──────────────────────────────┤
│ 07. NO SYSTEM CONFUSION      │ 08. INDEPENDENT REPLICATION  │
│ Model gains != Runtime hacks │ Must run on duplicate silicon│
└──────────────────────────────┴──────────────────────────────┘
```

### 8.1 Document series & numbering system

* `SMCo-TR-###`: formal technical reports (peer-reviewed internal monographs, e.g. `TR-001`).
* `RN-YYYY-###`: research notes (development signals and empirical observations).
* `NR-YYYY-###`: negative results (breakdowns, quantization collapse reports, preserved dead ends).
* `ST-YYYY-###`: technical standards & methodology manifestos.

---

## 9. Laboratory personnel & appointments

The laboratory directory is organized strictly by mid-century division of scientific
inquiry. These names correspond to the operating roles already defined in
[AGENTS.md](../../AGENTS.md) and [decision 0001](../decisions/0001-repository-governance.md);
keep any design use of these names consistent with those role definitions rather than
inventing new ones.

* **Principal Investigator & Director:** research direction, hardware synthesis, systems architecture.
* **Vesper (Research Associate):** mechanisms, recurrent dynamics, generalization boundaries.
* **Pyrrha (Research Associate):** evaluation contracts, structured representations, compositional holdouts.
* **Eido (Research Engineer):** compute allocation, manifest verification, physical bench reproducibility.

---

## 10. Physical ephemera & material artifacts

1. **Field research notebooks:** bound with heavy Manila card stock, industrial black spine tape, centered 16:1 mark, and numbered research registers (`FIELD RECORD NO. 88`).
2. **Lapel insignia:** 1.00 inch matte die-struck enamel pin. Black-oxide frame with a flush-inlaid Cadmium Ochre dense square. Worn by research fellows.
3. **Asset inventory seals:** heavy-duty anodized aluminum foil labels printed with permanent resin acrylic adhesive: `PROPERTY OF SMCo. / NEW HAVEN MODEL LABS / *SM-2026-9042*`.
4. **Calibration seals:** tamper-evident destructible cross-seam stickers applied across chassis split-lines.

---

**End of specification register.**
*Model Systems Laboratory · Crown & College Building · New Haven, Connecticut*
