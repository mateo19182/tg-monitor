"""Compare normal and Takeout history reads without writing archive messages."""
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telethon.errors import FloodWaitError, RPCError, TakeoutInitDelayError

from collect import row_from


async def run(client, handles, messages=1000, rounds=2):
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "messages_per_read": messages,
        "rounds": rounds,
        "scope": "History reads and row conversion; no archive writes or media downloads",
        "runs": [],
    }
    output = Path(__file__).resolve().parent / "data" / "takeout-benchmark.json"

    def save():
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")

    async def measure(reader, entity, anchor, mode, round_number):
        started = time.perf_counter()
        ids = []
        record = {"channel": entity.username, "mode": mode, "round": round_number,
                  "max_id": anchor, "wait_time": 1 if mode == "normal" else 0}
        try:
            async for msg in reader.iter_messages(
                entity, limit=messages, max_id=anchor, wait_time=record["wait_time"]
            ):
                row_from(msg, entity.id, result["started_at"])
                ids.append(msg.id)
            record["status"] = "ok"
        except FloodWaitError as error:
            record.update(status="flood_wait", wait_seconds=error.seconds)
            raise
        except RPCError as error:
            record.update(status="error", error=type(error).__name__)
            raise
        finally:
            elapsed = time.perf_counter() - started
            record.update(messages=len(ids), seconds=round(elapsed, 3),
                          messages_per_second=round(len(ids) / elapsed, 2),
                          ids_sha256=hashlib.sha256(json.dumps(ids).encode()).hexdigest())
            result["runs"].append(record)
            save()
            print(json.dumps(record), flush=True)

    # Surface server waits instead of silently including automatic sleeps in timings.
    threshold = client.flood_sleep_threshold
    client.flood_sleep_threshold = 0
    try:
        entities = []
        for handle in handles:
            entity = await client.get_entity(handle)
            latest = await client.get_messages(entity, limit=1)
            if not latest:
                raise ValueError(f"{handle}: no visible messages")
            entities.append((entity, latest[0].id + 1))
        async with client.takeout(channels=True, files=False) as takeout:
            for round_number in range(1, rounds + 1):
                # Alternate order to expose warm-cache and order effects.
                modes = ("normal", "takeout") if round_number % 2 else ("takeout", "normal")
                for entity, anchor in entities:
                    for mode in modes:
                        await measure(client if mode == "normal" else takeout,
                                      entity, anchor, mode, round_number)
        result["status"] = "complete"
        for entity, _ in entities:
            records = [r for r in result["runs"] if r["channel"] == entity.username]
            if len({r["ids_sha256"] for r in records}) != 1:
                result["status"] = "message_mismatch"
    except TakeoutInitDelayError as error:
        retry_at = datetime.now(timezone.utc) + timedelta(seconds=error.seconds + 60)
        result.update(status="initialization_delayed", retry_after_seconds=error.seconds,
                      retry_at=retry_at.isoformat())
        print(f"Takeout delayed until {result['retry_at']}; measuring normal reads", flush=True)
        try:
            for round_number in range(1, rounds + 1):
                for entity, anchor in entities:
                    await measure(client, entity, anchor, "normal", round_number)
        except (FloodWaitError, RPCError):
            pass  # keep the export retry deadline and the partial baseline
    except FloodWaitError as error:
        result.update(status="flood_wait", retry_after_seconds=error.seconds)
    except (RPCError, ValueError) as error:
        result.update(status="error", error=str(error))
    finally:
        client.flood_sleep_threshold = threshold
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps({"status": result["status"], "output": str(output),
                          "retry_after_seconds": result.get("retry_after_seconds")}), flush=True)
