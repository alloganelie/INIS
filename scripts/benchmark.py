"""Script de benchmark de performance pour INIS (§41.13).

Mesure :
  - Débit du pipeline (requêtes/sec)
  - Latences p50, p95, p99
  - Temps de calcul par étape
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from typing import Any

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID


async def run_benchmark(concurrency: int = 5, total_requests: int = 20) -> dict[str, Any]:
    print(f"Lancement du benchmark : {total_requests} requêtes avec concurrence {concurrency}...")
    runner = PipelineRunner()
    latencies: list[float] = []

    sem = asyncio.Semaphore(concurrency)

    async def _worker(idx: int) -> None:
        async with sem:
            req_id = ULID.new("REQ_")
            start = time.perf_counter()
            try:
                await runner.run(req_id, {"objective": f"Benchmark evaluation probe #{idx}"})
                duration = time.perf_counter() - start
                latencies.append(duration)
            except Exception as e:
                print(f"Erreur requête {req_id}: {e}")

    start_all = time.perf_counter()
    await asyncio.gather(*[_worker(i) for i in range(total_requests)])
    total_time = time.perf_counter() - start_all

    throughput = len(latencies) / total_time if total_time > 0 else 0
    sorted_lat = sorted(latencies)
    p50 = statistics.median(sorted_lat) if sorted_lat else 0.0
    p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0.0
    p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0.0

    report = {
        "total_requests": total_requests,
        "completed_requests": len(latencies),
        "total_time_seconds": round(total_time, 3),
        "throughput_req_per_sec": round(throughput, 2),
        "latencies_seconds": {
            "p50": round(p50, 4),
            "p95": round(p95, 4),
            "p99": round(p99, 4),
            "min": round(min(sorted_lat), 4) if sorted_lat else 0.0,
            "max": round(max(sorted_lat), 4) if sorted_lat else 0.0,
        },
    }
    print(json.dumps(report, indent=2))
    return report


def main() -> int:
    asyncio.run(run_benchmark())
    return 0


if __name__ == "__main__":
    main()

