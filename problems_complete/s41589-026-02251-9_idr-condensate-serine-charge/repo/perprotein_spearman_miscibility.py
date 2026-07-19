# perprotein_spearman_miscibility.py
# Per-protein Spearman: each protein vs 27 partners.
# Reproduces Extended Data Fig. 4b (heatmap), 4c (FYW-positive bar), 4d (EDKRH-negative bar).
# Grouping uses raw p < 0.05. FDR (per-column BH) written to Excel only.
# Input : AnalysisInputData.xlsx
#           sheet: IDR_Pair_Miscibility(Fig1b)
#           sheet: AA_composition_(28_IDRs)
# Output: perprotein_spearman_miscibility/

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import re, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import spearmanr, mannwhitneyu
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

def col_fdr(p_mat):
    """BH-FDR correction per column (per feature). For Excel output only."""
    fdr = np.ones_like(p_mat)
    for j in range(p_mat.shape[1]):
        col = p_mat[:, j]
        mask = ~np.isnan(col)
        if mask.sum() > 1:
            _, q, _, _ = multipletests(col[mask], method='fdr_bh')
            fdr[mask, j] = q
    return fdr

# ── Paths ──────────────────────────────────────────────────────────────────────
HERE    = os.path.dirname(os.path.abspath(__file__))
T2      = os.path.join(HERE, 'AnalysisInputData.xlsx')
T1      = os.path.join(HERE, 'AnalysisInputData.xlsx')
OUT_DIR = os.path.join(HERE, 'perprotein_spearman_miscibility')
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
proteins  = df_aa_idx.index.tolist()

# ── Per-protein Spearman ───────────────────────────────────────────────────────
print('=== Computing per-protein Spearman correlations ===')

rho_mat = np.full((len(proteins), len(feat_cols)), np.nan)
p_mat   = np.full((len(proteins), len(feat_cols)), np.nan)

for pi, host in enumerate(proteins):
    mask_host = (df_pairs['IDR1'] == host) | (df_pairs['IDR2'] == host)
    sub = df_pairs[mask_host].copy()
    sub['partner'] = sub.apply(
        lambda r: r['IDR2'] if r['IDR1'] == host else r['IDR1'], axis=1)
    sub = sub[sub['partner'].isin(df_aa_idx.index)]
    if len(sub) < 5:
        continue
    misc_host = sub[r_col].values.astype(float)
    for fi, fc in enumerate(feat_cols):
        partner_feat = df_aa_idx.loc[sub['partner'], fc].values.astype(float)
        mask = ~np.isnan(partner_feat) & ~np.isnan(misc_host)
        if mask.sum() < 5:
            continue
        rho, p = spearmanr(partner_feat[mask], misc_host[mask])
        rho_mat[pi, fi] = rho
        p_mat[pi, fi]   = p

# FDR per column — for Excel only, not used in plots or grouping
q_mat = col_fdr(p_mat)

# ── Fig b: Heatmap (raw p < 0.05 for black border) ────────────────────────────
print('=== Plotting heatmap (Fig b) ===')

COL_ORDER_LABELS = ['EDKRH', 'ED', 'KRH', 'D', 'E', 'K', 'R', 'H',
                    'FYW', 'Y', 'F', 'W', 'S', 'G', 'Q', 'N',
                    'A', 'C', 'I', 'L', 'M', 'P', 'T', 'V',
                    'NCPR', 'Hydropathy']
col_order_idx    = [feat_labels.index(l) for l in COL_ORDER_LABELS]
row_order_proteins = sorted(proteins)
row_order_idx    = [proteins.index(p) for p in row_order_proteins]

rho_plot = rho_mat[np.ix_(row_order_idx, col_order_idx)]
p_plot   = p_mat[np.ix_(row_order_idx, col_order_idx)]

n_rows = len(row_order_proteins)
n_cols = len(COL_ORDER_LABELS)
fig_w  = n_cols * 0.38 + 2.5
fig_h  = n_rows * 0.38 + 1.5

fig, ax = plt.subplots(figsize=(fig_w, fig_h))
fig.subplots_adjust(top=0.92, bottom=0.18, left=0.18, right=0.88)

vmax = 0.7
im = ax.imshow(rho_plot, aspect='auto', cmap='RdBu_r', vmin=-vmax, vmax=vmax,
               interpolation='nearest')

for ri in range(n_rows):
    for ci in range(n_cols):
        sig = not np.isnan(p_plot[ri, ci]) and p_plot[ri, ci] < 0.05
        lw  = 1.8 if sig else 0.3
        ec  = 'black' if sig else '#cccccc'
        rect = plt.Rectangle((ci - 0.5, ri - 0.5), 1, 1,
                              fill=False, edgecolor=ec, lw=lw)
        ax.add_patch(rect)

ax.set_xticks(range(n_cols))
ax.set_xticklabels(COL_ORDER_LABELS, rotation=90, fontsize=7,
                   fontweight='bold', fontfamily='Arial')
ax.set_yticks(range(n_rows))
ax.set_yticklabels(row_order_proteins, fontsize=7,
                   fontweight='bold', fontfamily='Arial')
ax.tick_params(axis='both', length=0)
for spine in ax.spines.values():
    spine.set_visible(False)

cb = plt.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
cb.set_label('Spearman ρ', fontsize=8, fontweight='bold', fontfamily='Arial',
             rotation=270, labelpad=12)
cb.ax.tick_params(labelsize=7)
for lbl in cb.ax.get_yticklabels():
    lbl.set_fontweight('bold'); lbl.set_fontfamily('Arial')

from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor='white', edgecolor='black', linewidth=1.8, label='p-value < 0.05'),
    Patch(facecolor='white', edgecolor='#cccccc', linewidth=0.3, label='non-significant'),
]
ax.legend(handles=legend_elements, loc='upper right', fontsize=6,
          frameon=True, framealpha=0.9,
          bbox_to_anchor=(1.0, 1.12), borderpad=0.5)

fig.text(0.5, 0.95, 'Per-protein Spearman ρ: partner feature vs miscibility',
         ha='center', fontsize=9, fontweight='bold', fontfamily='Arial')
fig.savefig(os.path.join(OUT_DIR, 'perprotein_heatmap.pdf'),
            bbox_inches='tight', dpi=300)
plt.close(fig)
print('Saved perprotein_heatmap.pdf')

# ── Grouping: raw p < 0.05 ────────────────────────────────────────────────────
fyw_idx   = feat_labels.index('FYW')
edkrh_idx = feat_labels.index('EDKRH')

fyw_pos_mask   = (rho_mat[:, fyw_idx]   > 0) & (p_mat[:, fyw_idx]   < 0.05)
edkrh_neg_mask = (rho_mat[:, edkrh_idx] < 0) & (p_mat[:, edkrh_idx] < 0.05)

print(f'FYW-positive group (rho>0, raw p<0.05): n={fyw_pos_mask.sum()}')
print(f'EDKRH-negative group (rho<0, raw p<0.05): n={edkrh_neg_mask.sum()}')

# ── Fig c/d: Group comparison bar charts ──────────────────────────────────────
def group_comparison(group_mask, group_name, out_pdf):
    group_proteins = [proteins[i] for i in range(len(proteins)) if group_mask[i]]
    other_proteins = [proteins[i] for i in range(len(proteins)) if not group_mask[i]]
    n_g = len(group_proteins); n_o = len(other_proteins)
    print(f'  {group_name}: n_targets={n_g}, n_others={n_o}')

    results = []
    for fc, fl in zip(feat_cols, feat_labels):
        g_vals = df_aa_idx.loc[
            [p for p in group_proteins if p in df_aa_idx.index], fc].values.astype(float)
        o_vals = df_aa_idx.loc[
            [p for p in other_proteins if p in df_aa_idx.index], fc].values.astype(float)
        g_vals = g_vals[~np.isnan(g_vals)]
        o_vals = o_vals[~np.isnan(o_vals)]
        if len(g_vals) < 2 or len(o_vals) < 2:
            results.append({'Feature': fl, 'N_targets': len(g_vals), 'N_others': len(o_vals),
                            'Median_targets': np.nan, 'Median_others': np.nan,
                            'Median_diff(A-B)': np.nan, 'U': np.nan, 'p_two_sided': np.nan})
            continue
        stat, p = mannwhitneyu(g_vals, o_vals, alternative='two-sided')
        results.append({
            'Feature':          fl,
            'N_targets':        len(g_vals),
            'N_others':         len(o_vals),
            'Median_targets':   float(np.median(g_vals)),
            'Median_others':    float(np.median(o_vals)),
            'Median_diff(A-B)': float(np.median(g_vals) - np.median(o_vals)),
            'U':                float(stat),
            'p_two_sided':      p,
        })

    df_res = pd.DataFrame(results)
    _, fdr, _, _ = multipletests(df_res['p_two_sided'].fillna(1), method='fdr_bh')
    df_res['FDR_BH'] = fdr
    df_res['direction'] = np.sign(df_res['Median_diff(A-B)'].fillna(0)).astype(int)
    df_res['neg_log10_q'] = -np.log10(df_res['FDR_BH'].clip(1e-10))
    df_res['signed_q'] = df_res['neg_log10_q'] * df_res['direction']
    df_plot = df_res.sort_values('signed_q')

    fig, ax = plt.subplots(figsize=(4.5, 6))
    fig.subplots_adjust(top=0.82, bottom=0.14, left=0.24, right=0.95)
    colors_b = ['#c0504d' if d > 0 else '#4472c4' for d in df_plot['direction']]
    y_pos = np.arange(len(df_plot))
    ax.barh(y_pos, df_plot['signed_q'], color=colors_b, height=0.7)
    ax.axvline(-np.log10(0.05), color='gray', ls='--', lw=0.9)
    ax.axvline( np.log10(0.05), color='gray', ls='--', lw=0.9)
    ax.axvline(0, color='black', lw=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(df_plot['Feature'], fontsize=8, fontweight='bold', fontfamily='Arial')
    ax.set_xlabel('Signed -log10(FDR)', fontsize=9, fontweight='bold', fontfamily='Arial')
    ax.tick_params(labelsize=8)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontweight('bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.text(0.5, 0.88, f'{group_name} vs others: sequence features',
             ha='center', fontsize=8, fontweight='bold', fontfamily='Arial')
    fig.savefig(os.path.join(OUT_DIR, out_pdf), bbox_inches='tight', dpi=300)
    plt.close(fig)
    print(f'  Saved {out_pdf}')

    return df_res[['Feature', 'N_targets', 'N_others', 'Median_targets',
                   'Median_others', 'Median_diff(A-B)', 'U', 'p_two_sided', 'FDR_BH']]

print('\n=== Plotting group comparison bars (Fig c, d) ===')
df_fyw_comp   = group_comparison(fyw_pos_mask,   'FYW-positive group',   'FYW_positive_group.pdf')
df_edkrh_comp = group_comparison(edkrh_neg_mask, 'EDKRH-negative group', 'EDKRH_negative_group.pdf')

# ── Save Excel ─────────────────────────────────────────────────────────────────
rows_long = []
for pi, prot in enumerate(proteins):
    for fi, fl in enumerate(feat_labels):
        rows_long.append({
            'Protein':        prot,
            'Feature':        fl,
            'SpearmanRho':    rho_mat[pi, fi],
            'P_value':        p_mat[pi, fi],
            'FDR_BH_per_col': q_mat[pi, fi],
        })
df_long = pd.DataFrame(rows_long)

with pd.ExcelWriter(os.path.join(OUT_DIR, 'perprotein_spearman_results.xlsx'),
                    engine='openpyxl') as writer:
    df_long.to_excel(writer, sheet_name='PerProtein_long', index=False)
    pd.DataFrame(rho_mat, index=proteins, columns=feat_labels).to_excel(
        writer, sheet_name='Rho_matrix')
    pd.DataFrame(p_mat, index=proteins, columns=feat_labels).to_excel(
        writer, sheet_name='Pvalue_matrix')
    pd.DataFrame(q_mat, index=proteins, columns=feat_labels).to_excel(
        writer, sheet_name='FDR_col_matrix')
    df_fyw_comp.to_excel(writer,   sheet_name='FYW_positive_group', index=False)
    df_edkrh_comp.to_excel(writer, sheet_name='EDKRH_negative_group', index=False)

print(f'\nAll outputs saved to {OUT_DIR}')
