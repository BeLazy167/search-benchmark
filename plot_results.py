#!/usr/bin/env python3
"""Render public aggregate results; never reads the private corpus."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data = json.loads(args.input.read_text())
    labels = {'fff-sdk': 'fff SDK', 'fff-mcp': 'fff MCP', 'ripgrep': 'ripgrep',
              'gnu-grep': 'GNU grep', 'ugrep': 'ugrep', 'grep': 'BSD grep'}
    rows = sorted(data['text'].items(), key=lambda item: item[1]['median_ms'])
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, (speed, correct) = plt.subplots(1, 2, figsize=(13, 6), gridspec_kw={'width_ratios': [1.3, 1]})
    fig.patch.set_facecolor('#f7f9fc')
    for ax in (speed, correct):
        ax.set_facecolor('#f7f9fc')
    names = [labels[k] for k, _ in rows]
    colors = ['#237b64' if r['exact_query_count'] == r['query_count'] else '#bc6518' for _, r in rows]
    speed.barh(names, [r['median_ms'] for _, r in rows], color=colors)
    speed.set_xscale('log')
    speed.set_xlim(1, max(r['median_ms'] for _, r in rows) * 4)
    speed.set_xlabel('Median milliseconds · logarithmic scale')
    speed.set_title('Literal search latency', loc='left', fontweight='bold')
    for i, (_, r) in enumerate(rows):
        speed.text(r['median_ms'] * 1.1, i, f"{r['median_ms']:.1f}", va='center')
    speed.invert_yaxis()
    correct.barh(names, [r['exact_query_count'] for _, r in rows], color=colors)
    correct.set_xlim(0, max(r['query_count'] for _, r in rows) * 1.2)
    correct.set_xlabel('Exact query sets across all 7 repetitions')
    correct.set_title('Correctness comes first', loc='left', fontweight='bold')
    for i, (_, r) in enumerate(rows):
        correct.text(r['exact_query_count'] + .5, i, f"{r['exact_query_count']}/{r['query_count']}", va='center')
    correct.invert_yaxis()
    corpus = data['corpus']
    fig.suptitle('Code search benchmark · October 15, 2026', x=.05, ha='left', fontsize=19, fontweight='bold')
    fig.text(.05, .89, f"{corpus['repo_count']} repositories · {corpus['file_count']:,} files · Apple M3 Pro · macOS 27.0")
    fig.text(.05, .035, 'SDK keeps an in-process index. CLI timings include startup. MCP results use different search semantics.\nPrivate source dataset; warm runs on a shared workstation. This is not a general tool ranking.', fontsize=10, color='#465568')
    fig.subplots_adjust(top=.80, bottom=.20, left=.10, right=.97, wspace=.40)
    fig.savefig(args.output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == '__main__':
    main()
