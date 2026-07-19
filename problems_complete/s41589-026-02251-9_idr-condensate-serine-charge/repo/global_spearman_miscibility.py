# global_spearman_miscibility.py
# Global Spearman correlation: 26 AA features vs miscibility across 378 IDR pairs.
# Reproduces Fig. 1f.
# Input : AnalysisInputData.xlsx
#           sheet: IDR_Pair_Miscibility(Fig1b)
#           sheet: AA_composition_(28_IDRs)
# Output: global_spearman_miscibility/

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import re, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from scipy.stats import spearmanr
from statsmodels.stats.multitest import multipletests
import openpyxl

# ── Helpers ────────────────────────────────────────────────────────────────────
def _strip_fig(name):
    return re.sub(r'\s*\([^)]*\)\s*', '', name).strip()

def read_sheet(path, keyword, **kwargs):
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
T2      = os.path.join(HERE, 'AnalysisInputData.xlsx')
T1      = os.path.join(HERE, 'AnalysisInputData.xlsx')
OUT_DIR = os.path.join(HERE, 'global_spearman_miscibility')
os.makedirs(OUT_DIR, exist_ok=True)

matplotlib.rcParams['font.family'] = 'Arial'
matplotlib.rcParams['axes.unicode_minus'] = False

# ── Load data ──────────────────────────────────────────────────────────────────
df_pairs = read_sheet(T2, 'IDR_Pair_Miscibility(Fig1b)')
df_aa    = read_sheet(T1, 'AA_composition_(28_IDRs)')

r_col = 'Miscibility(Pearson_r)'

feat_cols = ['FYW (fraction)', 'EDKRH (fraction)', 'ED (fraction)', 'KRH (fraction)',
             'A (fraction)', 'R (fraction)', 'N (fraction)', 'D (fraction)', 'C (fraction)',
             'Q (fraction)', 'E (fraction)', 'G (fraction)', 'H (fraction)',
             'I (fraction)', 'L (fraction)', 'K (fraction)', 'M (fraction)', 'F (fraction)',
             'P (fraction)', 'S (fraction)', 'T (fraction)', 'W (fraction)', 'Y (fraction)', 'V (fraction)',
             'NCPR (value)', 'Hydropathy (value)']
feat_labels = ['FYW', 'EDKRH', 'ED', 'KRH',
               'A', 'R', 'N', 'D', 'C', 'Q', 'E', 'G', 'H',
               'I', 'L', 'K', 'M', 'F', 'P', 'S', 'T', 'W', 'Y', 'V',
               'NCPR', 'Hydropathy']

df_aa_idx = df_aa.set_index('Protein name')

# ── Compute pairwise-averaged features ────────────────────────────────────────
pair_feats = []
for _, row in df_pairs.iterrows():
    p1, p2 = row['IDR1'], row['IDR2']
    if p1 in df_aa_idx.index and p2 in df_aa_idx.index:
        avg = (df_aa_idx.loc[p1, feat_cols].values.astype(float) +
               df_aa_idx.loc[p2, feat_cols].values.astype(float)) / 2
        pair_feats.append(avg)
    else:
        pair_feats.append(np.full(len(feat_cols), np.nan))

pair_feat_mat = np.array(pair_feats)
misc_scores   = df_pairs[r_col].values.astype(float)

# ── Spearman correlation ───────────────────────────────────────────────────────
results = []
for i, (fc, fl) in enumerate(zip(feat_cols, feat_labels)):
    x = pair_feat_mat[:, i]
    mask = ~np.isnan(x) & ~np.isnan(misc_scores)
    rho, p = spearmanr(x[mask], misc_scores[mask])
    results.append({'Feature': fl, 'Spearman_rho': rho, 'p_value': p, 'n': int(mask.sum())})

df_res = pd.DataFrame(results)
_, fdr, _, _ = multipletests(df_res['p_value'], method='fdr_bh')
df_res['FDR_BH'] = fdr
df_res['neg_log10_FDR'] = -np.log10(df_res['FDR_BH'].clip(1e-15))

# Sort by rho descending: FYW on top, K at bottom
df_res = df_res.sort_values('Spearman_rho', ascending=True)  # ascending=True for barh (top=largest)

print(df_res.to_string(index=False))

# ── Build continuous purple colorscale ────────────────────────────────────────
# Color: white (not significant) -> deep purple (highly significant)
# Driven by -log10(FDR), capped at 12
MAX_LOG = 12.0
norm = mcolors.Normalize(vmin=0, vmax=MAX_LOG)
cmap_purple = mcolors.LinearSegmentedColormap.from_list(
    'white_purple', ['#ffffff', '#3f007d'])

bar_colors = []
for _, row in df_res.iterrows():
    val = min(row['neg_log10_FDR'], MAX_LOG)
    bar_colors.append(cmap_purple(norm(val)))

# ── Plot ───────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(4.2, 7))
fig.subplots_adjust(top=0.88, bottom=0.10, left=0.22, right=0.80)

y_pos = np.arange(len(df_res))
bars = ax.barh(y_pos, df_res['Spearman_rho'], color=bar_colors, height=0.72,
               edgecolor='#888888', linewidth=0.3)

# Significance stars
for yi, (_, row) in zip(y_pos, df_res.iterrows()):
    p = row['p_value']
    if p < 0.001:   star = '***'
    elif p < 0.01:  star = '**'
    elif p < 0.05:  star = '*'
    else:           star = ''
    if star:
        x_star = row['Spearman_rho'] + (0.005 if row['Spearman_rho'] >= 0 else -0.005)
        ha = 'left' if row['Spearman_rho'] >= 0 else 'right'
        ax.text(x_star, yi, star, va='center', ha=ha, fontsize=7, color='black')

ax.axvline(0, color='#444', lw=0.8)
ax.set_yticks(y_pos)
ax.set_yticklabels(df_res['Feature'], fontsize=8, fontweight='bold', fontfamily='Arial')
ax.set_xlabel('Spearman ρ', fontsize=9, fontweight='bold', fontfamily='Arial')
ax.tick_params(labelsize=8)
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight('bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# Colorbar
sm = plt.cm.ScalarMappable(cmap=cmap_purple, norm=norm)
sm.set_array([])
cbar_ax = fig.add_axes([0.82, 0.10, 0.04, 0.78])
cb = fig.colorbar(sm, cax=cbar_ax)
cb.set_label('-log10(FDR)', fontsize=8, fontweight='bold',
             fontfamily='Arial', rotation=270, labelpad=14)
cb.ax.tick_params(labelsize=7)
for lbl in cb.ax.get_yticklabels():
    lbl.set_fontweight('bold'); lbl.set_fontfamily('Arial')

fig.text(0.5, 0.92, 'Global Spearman correlation: feature vs miscibility (n=378)',
         ha='center', fontsize=8, fontweight='bold', fontfamily='Arial')

fig.savefig(os.path.join(OUT_DIR, 'Fig1f_global_spearman_bar.pdf'),
            bbox_inches='tight', dpi=300)
plt.close(fig)
print('Saved Fig1f_global_spearman_bar.pdf')

# ── Save Excel ─────────────────────────────────────────────────────────────────
df_out = df_res[['Feature', 'Spearman_rho', 'p_value', 'FDR_BH', 'n']].sort_values(
    'Spearman_rho', ascending=False)
df_out.to_excel(os.path.join(OUT_DIR, 'global_spearman_results.xlsx'), index=False)
print(f'All outputs saved to {OUT_DIR}')
