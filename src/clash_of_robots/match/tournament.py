"""Tournament runner: N matches between two provider specs, colors swapped each round.

Usage:
    python -m clash_of_robots.match.tournament \
        --game 02_basic_mirror \
        --a random --b random --rounds 10

Prints a win/loss/draw table. Designed to be model-agnostic: pass any two
provider specs (including Claude models) and let it rip.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from clash_of_robots.harness.providers import make_provider
from clash_of_robots.match.run_match import run_match


def run_tournament(
    game: str,
    spec_a: str,
    spec_b: str,
    rounds: int,
    *,
    max_turns: int | None = None,
    replay_dir: Path | None = None,
    seed: int | None = None,
    cooldown_s: float = 0.0,
) -> dict:
    results = {"a_wins": 0, "b_wins": 0, "draws": 0, "matches": []}
    for r in range(rounds):
        # Alternate colors each round to remove first-player advantage.
        a_is_blue = r % 2 == 0
        if a_is_blue:
            blue_spec, red_spec = spec_a, spec_b
        else:
            blue_spec, red_spec = spec_b, spec_a
        blue = make_provider(blue_spec, seed=seed)
        red = make_provider(red_spec, seed=seed)
        replay_path = None
        if replay_dir is not None:
            replay_dir.mkdir(parents=True, exist_ok=True)
            replay_path = replay_dir / f"round_{r:03d}.jsonl"

        match = run_match(
            game=game,
            blue=blue,
            red=red,
            max_turns=max_turns,
            replay_path=replay_path,
            verbose=False,
        )
        winner_team = match["winner"]
        if winner_team is None:
            winner_spec = None
            results["draws"] += 1
        else:
            winner_spec = spec_a if ((winner_team == "blue") == a_is_blue) else spec_b
            if winner_spec == spec_a:
                results["a_wins"] += 1
            else:
                results["b_wins"] += 1

        results["matches"].append(
            {
                "round": r,
                "blue_spec": blue_spec,
                "red_spec": red_spec,
                "winner_team": winner_team,
                "winner_spec": winner_spec,
                "turns": match["turns"],
            }
        )
        if cooldown_s > 0 and r < rounds - 1:
            time.sleep(cooldown_s)

    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Clash Of Robots tournament")
    p.add_argument("--game", default="01_tiny_skirmish")
    p.add_argument("--a", required=True, help="provider spec A")
    p.add_argument("--b", required=True, help="provider spec B")
    p.add_argument("--rounds", type=int, default=6)
    p.add_argument("--max-turns", type=int, default=None)
    p.add_argument("--replay-dir", type=Path, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument(
        "--cooldown",
        type=float,
        default=0.0,
        help="seconds to sleep between matches (for LLM rate limits)",
    )
    args = p.parse_args()

    results = run_tournament(
        game=args.game,
        spec_a=args.a,
        spec_b=args.b,
        rounds=args.rounds,
        max_turns=args.max_turns,
        replay_dir=args.replay_dir,
        seed=args.seed,
        cooldown_s=args.cooldown,
    )
    n = args.rounds
    print(f"\nTournament: {args.a} vs {args.b} on {args.game} ({n} rounds)")
    print(f"  {args.a}: {results['a_wins']}/{n} wins ({results['a_wins'] / n:.1%})")
    print(f"  {args.b}: {results['b_wins']}/{n} wins ({results['b_wins'] / n:.1%})")
    print(f"  draws:  {results['draws']}/{n}")
    print("\nPer-round:")
    for m in results["matches"]:
        winner = m["winner_spec"] or "DRAW"
        print(
            f"  R{m['round']:>2}  blue={m['blue_spec']:<20} red={m['red_spec']:<20} "
            f"winner={winner:<20} turns={m['turns']}"
        )
    print("\n" + json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
