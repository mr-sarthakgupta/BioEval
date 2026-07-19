# phosphorylation_SaPS_phase_separation_analysis.py
# Phosphorylation vs phase separation analysis.
# Reproduces Fig. 5b, 5c, 5e.
# Input : AnalysisInputData.xlsx
#           sheets: Protein_PS_Predict, High_Phosph_for_GO, Core_Splicing_Protein
# Output: phosphorylation_phase_separation_analysis/

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import re, sys, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu, wilcoxon, fisher_exact
from statsmodels.stats.multitest import multipletests
import openpyxl

def _strip_fig(name):
    return re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()

def read_sheet(path, keyword, **kwargs):
    """Read Excel sheet by fuzzy keyword match, ignoring trailing (FigXX) suffixes."""
    kwargs.setdefault('engine', 'openpyxl')
    wb = openpyxl.load_workbook(path, read_only=True)
    sheets = wb.sheetnames
    wb.close()
    kw = _strip_fig(keyword).lower()
    for s in sheets:
        if s == keyword: return pd.read_excel(path, sheet_name=s, **kwargs)
    for s in sheets:
        if s.lower() == keyword.lower(): return pd.read_excel(path, sheet_name=s, **kwargs)
    for s in sheets:
        if _strip_fig(s).lower() == kw: return pd.read_excel(path, sheet_name=s, **kwargs)
    matches = [s for s in sheets if kw in _strip_fig(s).lower()]
    if len(matches) == 1: return pd.read_excel(path, sheet_name=matches[0], **kwargs)
    if len(matches) > 1:
        starts = [s for s in matches if _strip_fig(s).lower().startswith(kw)]
        if len(starts) == 1: return pd.read_excel(path, sheet_name=starts[0], **kwargs)
        raise ValueError(f"Ambiguous sheet '{keyword}': {matches}")
    raise ValueError(f"No sheet matching '{keyword}' in {path}.\nAvailable: {sheets}")

# ── Paths ──────────────────────────────────────────────────────────────────────
HERE    = os.path.dirname(os.path.abspath(__file__))
T4      = os.path.join(HERE, 'AnalysisInputData.xlsx')
OUT_DIR = os.path.join(HERE, 'phosphorylation_phase_separation_analysis')
os.makedirs(OUT_DIR, exist_ok=True)

matplotlib.rcParams['font.family'] = 'Arial'
matplotlib.rcParams['axes.unicode_minus'] = False

# ── Load Table 4a: protein PS prediction + phosphorylation status ──────────────
print('=== Module 1: Loading Table 4a ===')
df4a = read_sheet(T4, 'Protein_PS_Predict')
print(f'  Shape: {df4a.shape}')
print(f'  Columns: {df4a.columns.tolist()}')
print(df4a.head(3).to_string())

# ── Module 1: Fisher exact test (Fig 5b) ──────────────────────────────────────
# Classify proteins into PS/NoPS and Phos/No-Phos
# Expected columns: 'PS_status' (PS_Reported/PS_Predicted/NoPS), 'Phos_status' (Phos/No-Phos)
# Adapt column names based on actual data
ps_col   = [c for c in df4a.columns if 'PS' in c and 'status' in c.lower()]
phos_col = [c for c in df4a.columns if 'phos' in c.lower() and 'status' in c.lower()]

if ps_col and phos_col:
    ps_col, phos_col = ps_col[0], phos_col[0]
    df4a['is_PS']   = df4a[ps_col].astype(str).str.upper().isin(['PS_REPORTED', 'PS_PREDICTED', 'PS'])
    df4a['is_Phos'] = df4a[phos_col].astype(str).str.upper() == 'PHOS'

    ct = pd.crosstab(df4a['is_PS'], df4a['is_Phos'])
    print(f'\nContingency table (PS vs Phos):\n{ct}')
    odds, p_fisher = fisher_exact(ct.values)
    print(f'Fisher exact: OR={odds:.3f}, p={p_fisher:.3e}')

    # Bar chart (Fig 5b)
    fig, ax = plt.subplots(figsize=(4, 4))
    fig.subplots_adjust(top=0.82, bottom=0.15, left=0.18, right=0.95)
    categories = ['PS(Reported)', 'PS(Predicted)', 'NoPS']
    phos_counts = []
    nophos_counts = []
    for cat in categories:
        sub = df4a[df4a[ps_col].astype(str).str.contains(cat.replace('(', '').replace(')', ''),
                                                           case=False, na=False)]
        phos_counts.append((sub['is_Phos'] == True).sum())
        nophos_counts.append((sub['is_Phos'] == False).sum())
    x = np.arange(len(categories))
    ax.bar(x - 0.2, phos_counts,   0.35, label='Phos',    color='#c0504d', alpha=0.85)
    ax.bar(x + 0.2, nophos_counts, 0.35, label='No-Phos', color='#4472c4', alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=8, fontweight='bold', rotation=15)
    ax.set_ylabel('Protein count', fontsize=9, fontweight='bold')
    ax.legend(fontsize=8, frameon=False)
    ax.tick_params(labelsize=8)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontweight('bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.text(0.5, 0.88, f'PS vs Phosphorylation (Fisher p={p_fisher:.2e})',
             ha='center', fontsize=8, fontweight='bold')
    fig.savefig(os.path.join(OUT_DIR, 'PS_phosphorylation_protein_counts.pdf'), bbox_inches='tight', dpi=300)
    plt.close(fig)
    print('Saved PS_phosphorylation_protein_counts.pdf')
else:
    print('  Column names differ from expected — printing all columns for manual inspection:')
    print(df4a.columns.tolist())

# ── Module 2: S+Y fraction vs phosphorylation fraction scatter (Fig 5e) ───────
print('\n=== Module 2: S+Y fraction vs phosphorylation fraction (Fig 5e) ===')
df4b = read_sheet(T4, 'High_Phosph_for_GO')
df4c = read_sheet(T4, 'Core_Splicing_Protein')
print(f'  Table 4b shape: {df4b.shape}')
print(f'  Table 4c shape: {df4c.shape}')

x_col    = 'S/Y_Fraction'
y_col    = 'Phos_S/Y_Fraction'
name_col = 'Entry_Name'

x = pd.to_numeric(df4b[x_col], errors='coerce')
y = pd.to_numeric(df4b[y_col], errors='coerce')
mask = ~x.isna() & ~y.isna()

# Core splicing proteins (red circles, smaller than SRSF1)
splicing_names = set(df4c[name_col].astype(str).tolist())
is_srsf1 = df4b[name_col].astype(str).str.contains('SRSF1_HUMAN', na=False)
is_spl   = df4b[name_col].astype(str).apply(lambda n: n in splicing_names) & ~is_srsf1

fig, ax = plt.subplots(figsize=(5, 4.5))
fig.subplots_adjust(top=0.88, bottom=0.14, left=0.20, right=0.95)

# Background points
ax.scatter(x[mask & ~is_spl & ~is_srsf1], y[mask & ~is_spl & ~is_srsf1],
           s=8, color='#c4a882', alpha=0.35, linewidths=0, zorder=2)
# Core splicing (half size of SRSF1 = s=20)
ax.scatter(x[mask & is_spl], y[mask & is_spl],
           s=20, color='#c0504d', alpha=0.85, linewidths=0, zorder=3)
# SRSF1 (largest, s=40)
ax.scatter(x[mask & is_srsf1], y[mask & is_srsf1],
           s=40, color='#c0504d', alpha=1.0, linewidths=0, zorder=4)

# Annotate SRSF1
if (mask & is_srsf1).any():
    xi = x[mask & is_srsf1].values[0]
    yi = y[mask & is_srsf1].values[0]
    ax.annotate('SRSF1', (xi, yi), fontsize=8, fontweight='bold', color='#c0504d',
                xytext=(6, 2), textcoords='offset points')
    print(f'  SRSF1: S/Y={xi:.3f}, Phos={yi:.3f}')

ax.set_xlabel('S+Y fraction', fontsize=9, fontweight='bold')
ax.set_ylabel('Phosphorylation level\n(phospho S+Y/Total AAs)', fontsize=9, fontweight='bold')
ax.tick_params(labelsize=8)
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight('bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# Legend — placed outside plot area (upper left, no overlap)
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#c0504d',
           markersize=7, label='Core splicing proteins'),
    Line2D([0], [0], marker='o', color='w', markerfacecolor='#c4a882',
           markersize=5, label='Other IDRs'),
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=7,
          frameon=True, framealpha=0.9, edgecolor='#cccccc',
          bbox_to_anchor=(0.01, 0.99), borderpad=0.5)

fig.text(0.5, 0.93, 'SaPS score (WT)', ha='center', fontsize=9, fontweight='bold')
fig.savefig(os.path.join(OUT_DIR, 'SY_fraction_vs_phosphorylation_scatter.pdf'),
            bbox_inches='tight', dpi=300)
plt.close(fig)
print('Saved SY_fraction_vs_phosphorylation_scatter.pdf')

# ── Module 3: SaPS WT vs Phosphorylated scatter (Fig 5c) ──────────────────────
print('\n=== Module 3: SaPS WT vs Phosphorylated (Fig 5c) ===')
df4a = read_sheet(T4, 'Protein_PS_Predict')
wt_col   = 'SaPS(WT)'
phos_col = 'SaPS(S/Y_Phos)'

wt   = pd.to_numeric(df4a[wt_col],   errors='coerce')
phos = pd.to_numeric(df4a[phos_col], errors='coerce')

# Only proteins with at least one phosphorylation site (matches published analysis)
has_phos = pd.to_numeric(df4a['Num_Phos_S/Y'], errors='coerce') > 0
mask4a   = ~wt.isna() & ~phos.isna() & has_phos
print(f'  Proteins with phos sites: {mask4a.sum()}')

threshold = 0.5
crossed_up   = mask4a & (wt <  threshold) & (phos >= threshold)
crossed_down = mask4a & (wt >= threshold) & (phos <  threshold)
increased    = mask4a & (phos >  wt) & ~crossed_up  & ~crossed_down
decreased    = mask4a & (phos <= wt) & ~crossed_up  & ~crossed_down

n_up   = crossed_up.sum()
n_down = crossed_down.sum()
n_inc  = increased.sum()
n_dec  = decreased.sum()
print(f'  Crossed up={n_up}, Crossed down={n_down}, Increased={n_inc}, Decreased={n_dec}')

diff = phos[mask4a] - wt[mask4a]
diff_nz = diff[diff != 0]
_, p_wilcox = wilcoxon(diff_nz)
print(f'  Wilcoxon p={p_wilcox:.2e}  (n={len(diff_nz)})')

fig, ax = plt.subplots(figsize=(5, 5))
fig.subplots_adjust(top=0.92, bottom=0.13, left=0.14, right=0.95)

for cat_mask, color, zorder in [
    (decreased,    '#aaaaaa', 1),
    (increased,    '#333333', 2),
    (crossed_down, '#4caf50', 3),
    (crossed_up,   '#c0504d', 4),
]:
    ax.scatter(wt[cat_mask], phos[cat_mask],
               s=4, color=color, alpha=0.5, linewidths=0, zorder=zorder)

ax.axhline(threshold, color='#d4a017', ls='--', lw=0.8, alpha=0.7)
ax.axvline(threshold, color='#d4a017', ls='--', lw=0.8, alpha=0.7)
ax.plot([0, 1], [0, 1], color='#d4a017', lw=0.8, alpha=0.7)

ax.set_xlabel('SaPS score (WT)', fontsize=9, fontweight='bold')
ax.set_ylabel('SaPS score (S/Y_Phos)', fontsize=9, fontweight='bold')
ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
ax.tick_params(labelsize=8)
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight('bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

ax.text(0.05, 0.72, f'Wilcoxon p = {p_wilcox:.2e}',
        transform=ax.transAxes, fontsize=8, fontweight='bold')

from matplotlib.lines import Line2D
legend_elements = [
    Line2D([0],[0], marker='o', color='w', markerfacecolor='#c0504d', markersize=6,
           label=f'Crossed up (<0.5 to >=0.5) (n={n_up:,})'),
    Line2D([0],[0], marker='o', color='w', markerfacecolor='#4caf50', markersize=6,
           label=f'Crossed down (>=0.5 to <0.5) (n={n_down:,})'),
    Line2D([0],[0], marker='o', color='w', markerfacecolor='#333333', markersize=6,
           label=f'Increased (n={n_inc:,})'),
    Line2D([0],[0], marker='o', color='w', markerfacecolor='#aaaaaa', markersize=6,
           label=f'Decreased (n={n_dec:,})'),
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=6.5,
          frameon=True, framealpha=0.92, edgecolor='#cccccc',
          bbox_to_anchor=(0.01, 0.99), borderpad=0.5)

fig.savefig(os.path.join(OUT_DIR, 'SaPS_phospho_effect_scatter.pdf'),
            bbox_inches='tight', dpi=300)
plt.close(fig)
print('Saved SaPS_phospho_effect_scatter.pdf')

# ── Excel output ───────────────────────────────────────────────────────────────
print('\n=== Saving Excel output ===')

# Sheet 1: Input — Protein_PS_Predict (used for Fig 5c scatter)
df4a_out = read_sheet(T4, 'Protein_PS_Predict')

# Sheet 2: Input — High_Phosph_for_GO + Core_Splicing_Protein (used for Fig 5e scatter)
df4b_out = read_sheet(T4, 'High_Phosph_for_GO')
df4c_out = read_sheet(T4, 'Core_Splicing_Protein')

# Sheet 3: Results — SaPS scatter statistics (Fig 5c)
df_saps_stats = pd.DataFrame([{
    'n_total':        int(mask4a.sum()),
    'n_crossed_up':   int(n_up),
    'n_crossed_down': int(n_down),
    'n_increased':    int(n_inc),
    'n_decreased':    int(n_dec),
    'Wilcoxon_p':     float(p_wilcox),
    'threshold':      threshold,
}])

with pd.ExcelWriter(os.path.join(OUT_DIR, 'phosphorylation_SaPS_results.xlsx'),
                    engine='openpyxl') as writer:
    df4a_out.to_excel(writer, sheet_name='Input_Protein_PS_Predict', index=False)
    df4b_out.to_excel(writer, sheet_name='Input_High_Phosph_for_GO', index=False)
    df4c_out.to_excel(writer, sheet_name='Input_Core_Splicing_Protein', index=False)
    df_saps_stats.to_excel(writer, sheet_name='Results_SaPS_scatter_stats', index=False)

print('Saved phosphorylation_SaPS_results.xlsx')
print(f'\nAll outputs saved to {OUT_DIR}')
