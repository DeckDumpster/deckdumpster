from pathlib import Path

from mtg_collector.services.ocr import run_ocr, run_ocr_with_boxes

FIXTURE = str(Path(__file__).parent / "fixtures" / "one-card.jpg")


def test_ocr_one_card(capsys):
    texts = run_ocr(FIXTURE)
    fragments = run_ocr_with_boxes(FIXTURE)

    print("\n--- run_ocr ---")
    for t in texts:
        print(t)

    print("\n--- run_ocr_with_boxes ---")
    for f in fragments:
        print(f"{f['confidence']:.3f}  {f['bbox']}  {f['text']}")

    assert "Slingbow Trap" in texts
