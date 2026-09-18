"""Run the interpreter on all 10 public sample cases and compare to expected."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.schemas import OptimizeRequest
from app.interpreter import interpret_notes
from samples_loader import load_samples


def compare(case_id: str, expected: list, got: list) -> tuple[bool, str]:
    """Compare got vs expected directive_interpretation."""
    issues = []
    if len(got) != len(expected):
        return False, f"length mismatch: got {len(got)}, expected {len(expected)}"

    for i, (g, e) in enumerate(zip(got, expected)):
        if g.note_index != e["note_index"]:
            issues.append(f"[{i}] note_index mismatch: got {g.note_index}, expected {e['note_index']}")
            continue
        if g.applies != e["applies"]:
            issues.append(f"[{i}] applies mismatch: got {g.applies}, expected {e['applies']}")
        if g.directive_type != e["directive_type"]:
            issues.append(f"[{i}] directive_type mismatch: got {g.directive_type}, expected {e['directive_type']}")

        # Compare structured_adjustment fields
        e_adj = e.get("structured_adjustment")
        g_adj = g.structured_adjustment
        if e_adj is None and g_adj is not None:
            issues.append(f"[{i}] expected null adj, got {g_adj}")
        elif e_adj is not None and g_adj is None:
            issues.append(f"[{i}] expected adj {e_adj}, got null")
        elif e_adj is not None and g_adj is not None:
            for k, v in e_adj.items():
                if k not in g_adj:
                    issues.append(f"[{i}] missing key {k} in adj")
                elif g_adj[k] != v:
                    # Allow factor tolerance
                    if k == "factor" and isinstance(v, (int, float)) and abs(g_adj[k] - v) < 0.05:
                        continue
                    issues.append(f"[{i}] adj[{k}]: got {g_adj[k]}, expected {v}")

    if issues:
        return False, "; ".join(issues)
    return True, "OK"


def main():
    cases = load_samples()
    passed = 0
    for case in cases:
        inp = case["input"]
        req = OptimizeRequest(**inp)
        result = interpret_notes(req)
        expected = case["expected_output"]["directive_interpretation"]
        ok, msg = compare(case["id"], expected, result)
        status = "✓" if ok else "✗"
        print(f"{status} {case['id']}: {case['label']}")
        if not ok:
            print(f"    {msg}")
            print(f"    Got: {[(d.note_index, d.directive_type, d.structured_adjustment) for d in result]}")
            print(f"    Exp: {[(e['note_index'], e['directive_type'], e.get('structured_adjustment')) for e in expected]}")
        else:
            passed += 1
    print(f"\n{passed}/{len(cases)} passed")


if __name__ == "__main__":
    main()
