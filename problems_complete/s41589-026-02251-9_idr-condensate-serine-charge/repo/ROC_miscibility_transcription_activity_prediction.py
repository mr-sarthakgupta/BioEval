# ROC_miscibility_transcription_activity_prediction.py
# ROC/AUC analysis for miscibility vs transcriptional activity.
# Task A: Pol II nuclear miscibility predicts Activation/Repression class (Fig. 6e).
# Task B: transcriptional activity predicts High/Low miscibility class (Fig. 6f).
# Input : AnalysisInputData.xlsx
#           sheet: ROC_input_21IDRs(Fig6e,f)
# Output: ROC_miscibility_transcription_activity/

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import re, sys, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu
from sklearn.metrics import roc_curve, roc_auc_score
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
T5      = os.path.join(HERE, 'AnalysisInputData.xlsx')
OUT_DIR = os.path.join(HERE, 'ROC_miscibility_transcription_activity')
os.makedirs(OUT_DIR, exist_ok=True)

matplotlib.rcParams['font.family'] = 'Arial'
matplotlib.rcParams['axes.unicode_minus'] = False

# ── Load data ──────────────────────────────────────────────────────────────────
# Load pre-computed analysis input: log10_activity, PolII_miscibility, and binary labels
df_analysis = read_sheet(T5, 'ROC_input_21IDRs(Fig6e,f)')
name_col = 'Protein(IDR-SOX2)'

print('=== ROC input data (n=21) ===')
print(df_analysis.to_string())
print(f'\nActivation: {df_analysis["Activation_label"].sum()} positive, '
      f'{(df_analysis["Activation_label"]==0).sum()} negative')
print(f'High miscibility: {df_analysis["HighMisc_label"].sum()} positive, '
      f'{(df_analysis["HighMisc_label"]==0).sum()} negative')

# ── Bootstrap AUC CI ──────────────────────────────────────────────────────────
def bootstrap_auc_ci(y_true, y_score, n_boot=4000, seed=42, alpha=0.05):
    rng = np.random.default_rng(seed)
    aucs = []
    n = len(y_true)
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        if len(np.unique(y_true[idx])) < 2:
            continue
        aucs.append(roc_auc_score(y_true[idx], y_score[idx]))
    aucs = np.array(aucs)
    ci_lo = np.percentile(aucs, 100 * alpha / 2)
    ci_hi = np.percentile(aucs, 100 * (1 - alpha / 2))
    return ci_lo, ci_hi

# ── LOOCV Youden threshold ────────────────────────────────────────────────────
def loocv_youden(y_true, y_score):
    n = len(y_true)
    sensitivities, specificities, thresholds_used = [], [], []
    heldout_scores, heldout_labels = [], []
    for i in range(n):
        train_y = np.delete(y_true, i)
        train_s = np.delete(y_score, i)
        test_y  = y_true[i]
        test_s  = y_score[i]
        if len(np.unique(train_y)) < 2:
            continue
        fpr, tpr, thrs = roc_curve(train_y, train_s)
        youden = tpr - fpr
        best_thr = thrs[np.argmax(youden)]
        pred = int(test_s >= best_thr)
        sensitivities.append(int(pred == 1 and test_y == 1))
        specificities.append(int(pred == 0 and test_y == 0))
        thresholds_used.append(best_thr)
        heldout_scores.append(test_s)
        heldout_labels.append(test_y)
    tp_rate = np.mean(sensitivities) if sensitivities else np.nan
    tn_rate = np.mean(specificities) if specificities else np.nan
    # CV AUC from held-out scores
    try:
        cv_auc = roc_auc_score(heldout_labels, heldout_scores)
    except Exception:
        cv_auc = np.nan
    return tp_rate, tn_rate, np.mean(thresholds_used), np.std(thresholds_used), cv_auc

# ── Task A: miscibility → activation (Fig 6f) ─────────────────────────────────
print('\n=== Task A: Miscibility predicts Activation/Repression ===')
y_a = df_analysis['Activation_label'].values
s_a = df_analysis['PolII_miscibility'].values
mask_a = ~np.isnan(s_a)
y_a, s_a = y_a[mask_a], s_a[mask_a]

auc_a = roc_auc_score(y_a, s_a)
ci_lo_a, ci_hi_a = bootstrap_auc_ci(y_a, s_a)
_, p_mw_a = mannwhitneyu(s_a[y_a == 1], s_a[y_a == 0], alternative='two-sided')
sens_a, spec_a, thr_mean_a, thr_sd_a, cv_auc_a = loocv_youden(y_a, s_a)
fpr_a, tpr_a, _ = roc_curve(y_a, s_a)
# confusion matrix at Youden threshold on full data
youden_a = (tpr_a - fpr_a); best_thr_a = roc_curve(y_a, s_a)[2][np.argmax(youden_a)]
pred_a = (s_a >= best_thr_a).astype(int)
tp_a = int(((pred_a==1)&(y_a==1)).sum()); fp_a = int(((pred_a==1)&(y_a==0)).sum())
tn_a = int(((pred_a==0)&(y_a==0)).sum()); fn_a = int(((pred_a==0)&(y_a==1)).sum())
print(f'  AUC={auc_a:.4f}, 95%CI=[{ci_lo_a:.4f},{ci_hi_a:.4f}], p={p_mw_a:.4f}')
print(f'  LOOCV Sensitivity={sens_a:.4f}, Specificity={spec_a:.4f}, CV_AUC={cv_auc_a:.4f}')

# ── Task B: activity → high/low miscibility (Fig 6g) ──────────────────────────
print('\n=== Task B: Activity predicts High/Low miscibility ===')
y_b = df_analysis['HighMisc_label'].values
s_b = df_analysis['log10_activity'].values
mask_b = ~np.isnan(s_b) & ~np.isnan(y_b.astype(float))
y_b, s_b = y_b[mask_b], s_b[mask_b]

auc_b = roc_auc_score(y_b, s_b)
ci_lo_b, ci_hi_b = bootstrap_auc_ci(y_b, s_b)
_, p_mw_b = mannwhitneyu(s_b[y_b == 1], s_b[y_b == 0], alternative='two-sided')
sens_b, spec_b, thr_mean_b, thr_sd_b, cv_auc_b = loocv_youden(y_b, s_b)
fpr_b, tpr_b, _ = roc_curve(y_b, s_b)
# confusion matrix at Youden threshold on full data
youden_b = (tpr_b - fpr_b); best_thr_b = roc_curve(y_b, s_b)[2][np.argmax(youden_b)]
pred_b = (s_b >= best_thr_b).astype(int)
tp_b = int(((pred_b==1)&(y_b==1)).sum()); fp_b = int(((pred_b==1)&(y_b==0)).sum())
tn_b = int(((pred_b==0)&(y_b==0)).sum()); fn_b = int(((pred_b==0)&(y_b==1)).sum())
print(f'  AUC={auc_b:.4f}, 95%CI=[{ci_lo_b:.4f},{ci_hi_b:.4f}], p={p_mw_b:.4f}')
print(f'  LOOCV Sensitivity={sens_b:.4f}, Specificity={spec_b:.4f}, CV_AUC={cv_auc_b:.4f}')

# ── Plot ROC curves ────────────────────────────────────────────────────────────
def plot_roc(fpr, tpr, auc, ci_lo, ci_hi, title, out_name):
    fig, ax = plt.subplots(figsize=(4, 4))
    fig.subplots_adjust(top=0.82, bottom=0.14, left=0.16, right=0.95)
    ax.plot(fpr, tpr, 'o-', color='#c0504d', ms=4, lw=1.5,
            label=f'AUC={auc:.3f}\n95%CI=[{ci_lo:.3f},{ci_hi:.3f}]')
    ax.plot([0, 1], [0, 1], 'k--', lw=0.8, alpha=0.5)
    ax.set_xlabel('False Positive Rate', fontsize=9, fontweight='bold')
    ax.set_ylabel('True Positive Rate', fontsize=9, fontweight='bold')
    ax.legend(fontsize=8, frameon=False, loc='lower right')
    ax.tick_params(labelsize=8)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_fontweight('bold')
    ax.set_xlim(-0.02, 1.02); ax.set_ylim(-0.02, 1.02)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.text(0.5, 0.88, title, ha='center', fontsize=8, fontweight='bold')
    fig.savefig(os.path.join(OUT_DIR, out_name), bbox_inches='tight', dpi=300)
    plt.close(fig)
    print(f'Saved {out_name}')

plot_roc(fpr_a, tpr_a, auc_a, ci_lo_a, ci_hi_a,
         'Task A: Miscibility predicts Activation/Repression (n=21)',
         'ROC_miscibility_predicts_activation.pdf')
plot_roc(fpr_b, tpr_b, auc_b, ci_lo_b, ci_hi_b,
         'Task B: Activity predicts High/Low Miscibility (n=21)',
         'ROC_activity_predicts_miscibility.pdf')

# ── Save results ───────────────────────────────────────────────────────────────
summary = pd.DataFrame([
    {'dataset': 'n=21 (excl. TDP43,MED1,hnRNPH1,BRD4,PRCC,HES4)',
     'task': 'A: Miscibility -> Activation/Repression',
     'in_sample_AUC': auc_a, 'CI_lo': ci_lo_a, 'CI_hi': ci_hi_a,
     'p_MannWhitney': p_mw_a,
     'n': len(y_a), 'tp': tp_a, 'fp': fp_a, 'tn': tn_a, 'fn': fn_a,
     'LOOCV_Sensitivity': sens_a, 'LOOCV_Specificity': spec_a,
     'mean_threshold': thr_mean_a, 'sd_threshold': thr_sd_a,
     'CV_AUC_from_heldout_scores': cv_auc_a},
    {'dataset': 'n=21 (excl. TDP43,MED1,hnRNPH1,BRD4,PRCC,HES4)',
     'task': 'B: Activity -> High/Low Miscibility',
     'in_sample_AUC': auc_b, 'CI_lo': ci_lo_b, 'CI_hi': ci_hi_b,
     'p_MannWhitney': p_mw_b,
     'n': len(y_b), 'tp': tp_b, 'fp': fp_b, 'tn': tn_b, 'fn': fn_b,
     'LOOCV_Sensitivity': sens_b, 'LOOCV_Specificity': spec_b,
     'mean_threshold': thr_mean_b, 'sd_threshold': thr_sd_b,
     'CV_AUC_from_heldout_scores': cv_auc_b},
])

with pd.ExcelWriter(os.path.join(OUT_DIR, 'ROC_AUC_results.xlsx'), engine='openpyxl') as writer:
    summary.to_excel(writer, sheet_name='ROC_AUC_summary_both_tasks', index=False)
    df_analysis[[name_col, 'log10_activity', 'PolII_miscibility',
                 'Activation_label', 'HighMisc_label']].to_excel(
        writer, sheet_name='ROC_Analysis_input_21IDRs', index=False)

print(f'\nAll outputs saved to {OUT_DIR}')
