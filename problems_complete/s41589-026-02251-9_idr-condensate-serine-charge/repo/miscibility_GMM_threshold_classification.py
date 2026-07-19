# miscibility_GMM_threshold_classification.py
# Two-component GMM on 378 pairwise miscibility scores.
# Reproduces Extended Data Fig. 1j
# Determines the miscible/immiscible classification threshold (r ~ 0.45).
# Input : AnalysisInputData.xlsx
#           sheet: IDR_Pair_Miscibility(Fig1b)
# Output: GMM_miscibility_threshold/

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import re, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import norm
from scipy.optimize import brentq
from sklearn.mixture import GaussianMixture
import openpyxl

HERE    = os.path.dirname(os.path.abspath(__file__))
T2      = os.path.join(HERE, 'AnalysisInputData.xlsx')
OUT_DIR = os.path.join(HERE, 'GMM_miscibility_threshold')
os.makedirs(OUT_DIR, exist_ok=True)

matplotlib.rcParams['font.family'] = 'Arial'
matplotlib.rcParams['axes.unicode_minus'] = False

# ── Fuzzy sheet reader ─────────────────────────────────────────────────────────
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

# ── Load data ──────────────────────────────────────────────────────────────────
df_pairs = read_sheet(T2, 'IDR_Pair_Miscibility(Fig1b)')
r_col    = 'Miscibility(Pearson_r)'
scores   = df_pairs[r_col].values.astype(float)
print(f'Loaded {len(scores)} pairwise miscibility scores')
print(f'  range: [{scores.min():.4f}, {scores.max():.4f}]')

# ── GMM fitting ────────────────────────────────────────────────────────────────
gmm = GaussianMixture(n_components=2, random_state=42)
gmm.fit(scores.reshape(-1, 1))

means  = gmm.means_.flatten()
order  = np.argsort(means)
mu_lo, mu_hi   = means[order]
w_lo,  w_hi    = gmm.weights_[order]
var_lo, var_hi = gmm.covariances_.flatten()[order]

print(f'\nGMM components:')
print(f'  Low  component: mean={mu_lo:.4f}, std={np.sqrt(var_lo):.4f}, weight={w_lo:.4f}')
print(f'  High component: mean={mu_hi:.4f}, std={np.sqrt(var_hi):.4f}, weight={w_hi:.4f}')

def _gmm_diff(x):
    return (w_lo * norm.pdf(x, mu_lo, np.sqrt(var_lo)) -
            w_hi * norm.pdf(x, mu_hi, np.sqrt(var_hi)))

threshold    = brentq(_gmm_diff, mu_lo, mu_hi)
n_miscible   = (scores >= threshold).sum()
n_immiscible = (scores <  threshold).sum()
print(f'\nGMM threshold (intersection): r = {threshold:.4f}')
print(f'  Miscible pairs   (r >= {threshold:.2f}): {n_miscible}')
print(f'  Immiscible pairs (r <  {threshold:.2f}): {n_immiscible}')

# ── Plot ───────────────────────────────────────────────────────────────────────
x_range = np.linspace(-0.3, 1.1, 600)
fig, ax = plt.subplots(figsize=(5, 3.5))
fig.subplots_adjust(top=0.82, bottom=0.15, left=0.14, right=0.95)

ax.hist(scores, bins=30, density=True, color='#cccccc', edgecolor='white',
        label='Observed (n=378)')
ax.plot(x_range,
        w_lo * norm.pdf(x_range, mu_lo, np.sqrt(var_lo)) +
        w_hi * norm.pdf(x_range, mu_hi, np.sqrt(var_hi)),
        'k-', lw=1.5, label='GMM fit')
ax.plot(x_range, w_lo * norm.pdf(x_range, mu_lo, np.sqrt(var_lo)),
        'r--', lw=1.2, label=f'Low (mu={mu_lo:.2f})')
ax.plot(x_range, w_hi * norm.pdf(x_range, mu_hi, np.sqrt(var_hi)),
        'b--', lw=1.2, label=f'High (mu={mu_hi:.2f})')
ax.axvline(threshold, color='green', ls='--', lw=1.2,
           label=f'Threshold r={threshold:.2f}')

ax.set_xlabel('Miscibility score (Pearson r)', fontsize=9, fontweight='bold')
ax.set_ylabel('Density', fontsize=9, fontweight='bold')
ax.tick_params(labelsize=8)
for lbl in ax.get_xticklabels() + ax.get_yticklabels():
    lbl.set_fontweight('bold')
ax.legend(fontsize=7, frameon=False)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

stat_str = (f'Low: mu={mu_lo:.2f}, High: mu={mu_hi:.2f} | '
            f'Threshold={threshold:.2f} | '
            f'Miscible={n_miscible}, Immiscible={n_immiscible}')
fig.text(0.5, 0.88,
         'GMM decomposition of pairwise miscibility scores (n=378)',
         ha='center', fontsize=9, fontweight='bold')
fig.text(0.5, 0.84, stat_str, ha='center', fontsize=7, color='#444')

fig.savefig(os.path.join(OUT_DIR, 'miscibility_GMM_two_component.pdf'),
            bbox_inches='tight', dpi=300)
plt.close(fig)
print('Saved miscibility_GMM_two_component.pdf')

# ── Save results to Excel ──────────────────────────────────────────────────────
df_gmm = pd.DataFrame({
    'Component':  ['Low (immiscible)', 'High (miscible)'],
    'Mean':       [mu_lo, mu_hi],
    'Std':        [np.sqrt(var_lo), np.sqrt(var_hi)],
    'Weight':     [w_lo, w_hi],
})
df_thresh = pd.DataFrame({
    'GMM_threshold':  [threshold],
    'n_miscible':     [n_miscible],
    'n_immiscible':   [n_immiscible],
})
with pd.ExcelWriter(os.path.join(OUT_DIR, 'GMM_miscibility_results.xlsx'),
                    engine='openpyxl') as writer:
    df_gmm.to_excel(writer,    sheet_name='GMM_two_components', index=False)
    df_thresh.to_excel(writer, sheet_name='Classification_threshold', index=False)

print(f'\nAll outputs saved to {OUT_DIR}')
