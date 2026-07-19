# IDR_miscibility_hierarchical_cluster_heatmap.py
# Hierarchical clustering of 28 IDRs by miscibility profile.
# Produces dendrogram, intra-cluster boxplot, and AA composition heatmap.
# Reproduces Extended Data Fig. 3a, 3b, 3c.
# Input : AnalysisInputData.xlsx
#           sheet: IDR_Pair_Miscibility(Fig1b)
#           sheet: AA_composition_(28_IDRs)
# Output: IDR_hierarchical_clustering/

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import re, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.spatial.distance import pdist
from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from scipy.stats import mannwhitneyu
import openpyxl

HERE    = os.path.dirname(os.path.abspath(__file__))
T1      = os.path.join(HERE, 'AnalysisInputData.xlsx')
T2      = os.path.join(HERE, 'AnalysisInputData.xlsx')
OUT_DIR = os.path.join(HERE, 'IDR_hierarchical_clustering')
os.makedirs(OUT_DIR, exist_ok=True)

matplotlib.rcParams['font.family'] = 'Arial'
matplotlib.rcParams['axes.unicode_minus'] = False

# ── Fuzzy sheet reader ─────────────────────────────────────────────────────────
def _strip_fig(name):
    return re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()

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

# ── Module 1: Load data & build similarity matrix ─────────────────────────────
print('=== Module 1: Load data ===')
df_pairs = read_sheet(T2, 'IDR_Pair_Miscibility(Fig1b)')
df_aa    = read_sheet(T1, 'AA_composition_(28_IDRs)')
r_col    = 'Miscibility(Pearson_r)'

proteins = list(dict.fromkeys(df_pairs['IDR1'].tolist() + df_pairs['IDR2'].tolist()))
n   = len(proteins)
idx = {p: i for i, p in enumerate(proteins)}
print(f'  {n} proteins loaded')

sim_mat = np.full((n, n), np.nan)
np.fill_diagonal(sim_mat, 1.0)
for _, row in df_pairs.iterrows():
    p1, p2 = row['IDR1'], row['IDR2']
    if p1 in idx and p2 in idx:
        i, j = idx[p1], idx[p2]
        sim_mat[i, j] = sim_mat[j, i] = row[r_col]

# ── Module 2: Hierarchical clustering ─────────────────────────────────────────
print('\n=== Module 2: Hierarchical clustering ===')
sim_filled = np.where(np.isnan(sim_mat), 0.0, sim_mat)
dist_vec   = pdist(sim_filled, metric='euclidean')
Z          = linkage(dist_vec, method='average')
labels_7   = fcluster(Z, t=7, criterion='maxclust')
cluster_df = pd.DataFrame({'Protein_Name': proteins, 'Cluster': labels_7})
print('Cluster assignments:')
print(cluster_df.to_string(index=False))

# ── Module 3: Dendrogram ──────────────────────────────────────────────────────
print('\n=== Module 3: Dendrogram ===')
fig, ax = plt.subplots(figsize=(10, 6))
dendrogram(Z, labels=proteins, ax=ax, leaf_rotation=90, leaf_font_size=7)
ax.set_ylabel('Euclidean distance (miscibility vectors)', fontsize=9, fontweight='bold')
ax.tick_params(labelsize=7)
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight('bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
fig.suptitle('Hierarchical Clustering of 28 Proteins', fontsize=10, fontweight='bold')
fig.tight_layout()
fig.savefig(os.path.join(OUT_DIR, 'IDR_cluster_dendrogram_28proteins.pdf'),
            bbox_inches='tight', dpi=300)
plt.close(fig)
print('Saved IDR_cluster_dendrogram_28proteins.pdf')

# ── Module 4: Intra-cluster miscibility boxplot ───────────────────────────────
print('\n=== Module 4: Intra-cluster miscibility ===')
cluster_sizes  = cluster_df['Cluster'].value_counts()
multi_clusters = sorted(cluster_sizes[cluster_sizes > 1].index.tolist())

intra_scores = {}
for c in multi_clusters:
    members = cluster_df[cluster_df['Cluster'] == c]['Protein_Name'].tolist()
    vals = []
    for i, p1 in enumerate(members):
        for p2 in members[i+1:]:
            if p1 in idx and p2 in idx:
                r = sim_mat[idx[p1], idx[p2]]
                if not np.isnan(r):
                    vals.append(r)
    intra_scores[f'C{c}'] = vals
    print(f'  C{c}: {len(members)} members, {len(vals)} pairs, mean r={np.mean(vals):.3f}')

c_means = {k: np.mean(v) for k, v in intra_scores.items()}
c_ref   = min(c_means, key=c_means.get)
print(f'  Reference cluster (lowest mean): {c_ref}')

labels_c  = list(intra_scores.keys())
data_list = [intra_scores[k] for k in labels_c]
positions = list(range(len(labels_c)))
rng = np.random.default_rng(42)

fig, ax = plt.subplots(figsize=(5, 4))
fig.subplots_adjust(top=0.82, bottom=0.12, left=0.15, right=0.95)
bp = ax.boxplot(data_list, positions=positions, patch_artist=True, widths=0.5,
                medianprops=dict(color='black', linewidth=2),
                flierprops=dict(marker='', markersize=0))
for patch in bp['boxes']:
    patch.set_facecolor('#4472C4'); patch.set_alpha(0.6)
for pos, vals in zip(positions, data_list):
    jitter = rng.uniform(-0.12, 0.12, size=len(vals))
    ax.scatter(pos + jitter, vals, color='#1a3a6b', alpha=0.7, s=18, zorder=3, linewidths=0)

ax.set_xticks(positions)
ax.set_xticklabels(labels_c, fontsize=8, fontweight='bold')
ax.set_ylabel('Intra-cluster miscibility (Pearson r)', fontsize=9, fontweight='bold')
ax.tick_params(labelsize=8)
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight('bold')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

ref_vals = intra_scores[c_ref]
y_max    = max(max(v) for v in data_list) + 0.05
for i, (k, vals) in enumerate(intra_scores.items()):
    if k == c_ref:
        continue
    _, p = mannwhitneyu(vals, ref_vals, alternative='two-sided')
    if p < 0.05:
        ax.text(i, y_max, f'p={p:.3f}', ha='center', fontsize=7, fontweight='bold')

fig.text(0.5, 0.88, 'Intra-cluster miscibility by cluster',
         ha='center', fontsize=9, fontweight='bold')
fig.savefig(os.path.join(OUT_DIR, 'intracluster_miscibility_boxplot.pdf'),
            bbox_inches='tight', dpi=300)
plt.close(fig)
print('Saved intracluster_miscibility_boxplot.pdf')

# ── Module 5: Cluster AA composition heatmap ─────────────────────────────────
print('\n=== Module 5: Cluster composition heatmap ===')

FEAT_COLS_ORDERED = [
    'V (fraction)', 'P (fraction)', 'M (fraction)', 'L (fraction)', 'I (fraction)', 'C (fraction)', 'N (fraction)', 'Q (fraction)', 'T (fraction)',
    'A (fraction)', 'G (fraction)', 'S (fraction)',
    'W (fraction)', 'Y (fraction)', 'F (fraction)', 'FYW (fraction)',
    'H (fraction)', 'R (fraction)', 'K (fraction)', 'D (fraction)', 'E (fraction)', 'ED (fraction)', 'KRH (fraction)', 'EDKRH (fraction)',
]
FEAT_LABELS_ORDERED = [
    'V', 'P', 'M', 'L', 'I', 'C', 'N', 'Q', 'T',
    'A', 'G', 'S',
    'W', 'Y', 'F', 'FYW',
    'H', 'R', 'K', 'D', 'E', 'ED', 'KRH', 'EDKRH',
]
BRACKETS = [
    ('Aromatic\nresidues', 12,  15),
    ('Charged\nresidues',  16,  23),
]

df_aa_idx = df_aa.set_index('Protein name')
CLUSTER_ROW_ORDER = [1, 3, 4, 5, 6]
cluster_feat = {}
for c in CLUSTER_ROW_ORDER:
    if c not in cluster_df['Cluster'].values:
        continue
    members = cluster_df[cluster_df['Cluster'] == c]['Protein_Name'].tolist()
    sub = df_aa_idx.loc[[m for m in members if m in df_aa_idx.index], FEAT_COLS_ORDERED]
    cluster_feat[f'Cluster {c}'] = sub.mean()
    print(f'  Cluster {c}: {members}')

feat_mat = pd.DataFrame(cluster_feat).T

def piecewise_norm(val):
    v = float(np.clip(val, 0.0, 0.40))
    return (0.75 * v / 0.20) if v <= 0.20 else (0.75 + 0.25 * (v - 0.20) / 0.20)

norm_mat = feat_mat.applymap(piecewise_norm)
n_cols = len(FEAT_LABELS_ORDERED)
n_rows = len(feat_mat)

fig, ax = plt.subplots(figsize=(n_cols * 0.42 + 2.5, n_rows * 0.55 + 1.8))
fig.subplots_adjust(top=0.82, bottom=0.32, left=0.13, right=0.88)
im = ax.imshow(norm_mat.values, aspect='auto', cmap='Reds', vmin=0, vmax=1,
               interpolation='nearest')

ax.set_xticks(range(n_cols))
ax.set_xticklabels(FEAT_LABELS_ORDERED, rotation=90, fontsize=8,
                   fontweight='bold', fontfamily='Arial')
ax.set_yticks(range(n_rows))
ax.set_yticklabels(feat_mat.index, fontsize=8, fontweight='bold', fontfamily='Arial')
ax.tick_params(axis='both', length=0)
for spine in ax.spines.values():
    spine.set_visible(False)

cb_ticks_real = [0.0, 0.1, 0.2, 0.3]
cb = plt.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
cb.set_ticks([piecewise_norm(v) for v in cb_ticks_real])
cb.set_ticklabels([f'{v:.1f}' for v in cb_ticks_real])
cb.set_label('Mean AA fraction per cluster', fontsize=7, fontweight='bold',
             fontfamily='Arial', rotation=270, labelpad=12)
cb.ax.tick_params(labelsize=7)
for lbl in cb.ax.get_yticklabels():
    lbl.set_fontweight('bold'); lbl.set_fontfamily('Arial')

for label, i_start, i_end in BRACKETS:
    ax.annotate('', xy=(i_end + 0.4, -1.5), xytext=(i_start - 0.4, -1.5),
                xycoords='data', textcoords='data',
                arrowprops=dict(arrowstyle='-', color='black', lw=1.0),
                annotation_clip=False)
    for xi in [i_start - 0.4, i_end + 0.4]:
        ax.plot([xi, xi], [-1.5, -1.2], color='black', lw=1.0,
                transform=ax.transData, clip_on=False)
    ax.text((i_start + i_end) / 2.0, -2.2, label,
            ha='center', va='top', fontsize=7, fontweight='bold',
            fontfamily='Arial', transform=ax.transData, clip_on=False)

fig.text(0.5, 0.88, 'Mean amino acid composition by cluster',
         ha='center', fontsize=9, fontweight='bold', fontfamily='Arial')
fig.savefig(os.path.join(OUT_DIR, 'cluster_AA_composition_heatmap.pdf'),
            bbox_inches='tight', dpi=300)
plt.close(fig)
print('Saved cluster_AA_composition_heatmap.pdf')

# ── Save to Excel ──────────────────────────────────────────────────────────────
with pd.ExcelWriter(os.path.join(OUT_DIR, 'IDR_clustering_results.xlsx'),
                    engine='openpyxl') as writer:
    cluster_df.to_excel(writer, sheet_name='Protein_cluster_assignments', index=False)
    feat_mat.to_excel(writer,   sheet_name='Cluster_mean_AA_fractions')

print(f'\nAll outputs saved to {OUT_DIR}')
