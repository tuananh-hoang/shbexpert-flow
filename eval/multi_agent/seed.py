"""Seed 24 golden case vào Postgres/MinIO, dùng lại nguyên
`scripts/seed_synthetic_cases.py::_seed_one` (idempotent).

Chạy qua container `api` chứ không phải `worker`: chỉ image api mới có gói
`minio` mà _seed_one cần để render và upload PDF chứng từ.

    docker compose run --rm -v ./artifacts:/app/artifacts -v ./eval:/app/eval \\
        api python -m eval.multi_agent.seed
"""
from __future__ import annotations

import scripts.seed_synthetic_cases as seeder

from eval.common.scoring import load_golden

# _seed_one đọc case.json từ CASES_DIR; bộ eval nằm ở artifacts/eval_cases/ chứ
# không phải artifacts/cases/, nên trỏ lại đường dẫn thay vì nhân bản logic seed.
seeder.CASES_DIR = seeder.Path(__file__).resolve().parent.parent.parent / "artifacts" / "eval_cases"


def main() -> None:
    ok = 0
    for case_id in load_golden():
        if seeder._seed_one(case_id):
            ok += 1
    print(f"seeded {ok} case(s) moi; cac case con lai da ton tai (idempotent)")


if __name__ == "__main__":
    main()
