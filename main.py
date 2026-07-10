"""Run the full process-quality modeling and BO recommendation workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.bayes_opt import BO_COLUMNS, recommend_bo
from src.features import add_engineered_features, available_feature_columns
from src.importance import build_feature_importance, build_response_curves
from src.io_utils import ensure_directories, load_config, read_table, resolve_input_files, setup_logging
from src.bo_compatibility import (
    export_task_logs,
    feedback_json,
    init_task,
    load_task_state,
    recommend_next,
    recommend_parameters,
    run_json,
    save_task_state,
    submit_feedback,
)
from src.models import fit_models_for_target, select_best_models, summarize_performance
from src.plotting import plot_bo_maps, plot_feature_importance, plot_pred_vs_true, plot_response_curve
from src.preprocessing import build_data_quality_report, clean_material_table, combine_cleaned_tables, write_schema_summary
from src.report import generate_modeling_report


MILLING_TARGETS = ["depth_um", "Sa_um"]
CUTTING_TARGETS = ["cut_through", "kerf_top_width_um", "kerf_taper_deg", "cut_edge_Sa_um", "chipping_um"]


def run(config_path: str | Path) -> None:
    """Execute the reproducible modeling workflow from a config file."""
    root = Path(config_path).resolve().parent
    config = load_config(config_path)
    dirs = ensure_directories(root)
    logger = setup_logging(dirs["outputs"])
    logger.info("Starting workflow with config: %s", config_path)

    cleaned_tables = []
    source_summaries = []
    for material, path in resolve_input_files(config, root).items():
        if not path.exists():
            raise FileNotFoundError(f"Input file not found for {material}: {path}")
        for raw_df, metadata in read_table(path):
            cleaned, summary = clean_material_table(raw_df, material, metadata)
            cleaned_tables.append(cleaned)
            source_summaries.append(summary)
            logger.info("Loaded %s from %s: %s rows", material, path.name, len(cleaned))

    unified = combine_cleaned_tables(cleaned_tables)
    quality = build_data_quality_report(unified)
    unified_path = dirs["data_processed"] / "unified_experiments.csv"
    quality_path = dirs["data_processed"] / "data_quality_report.csv"
    unified.to_csv(unified_path, index=False, encoding="utf-8-sig")
    quality.to_csv(quality_path, index=False, encoding="utf-8-sig")
    write_schema_summary(dirs["outputs"] / "data_schema_summary.md", unified, source_summaries, quality)

    featured = add_engineered_features(unified)
    featured.to_csv(dirs["data_processed"] / "unified_experiments_with_features.csv", index=False, encoding="utf-8-sig")

    random_seed = int(config.get("random_seed", 42))
    cv_max_folds = int(config.get("cv_max_folds", 5))
    all_results = []
    for (process_type, material), group in featured.groupby(["process_type", "material"]):
        feature_columns = available_feature_columns(group)
        targets = CUTTING_TARGETS if process_type == "cutting" else MILLING_TARGETS
        for target in targets:
            if group[target].notna().sum() == 0:
                logger.warning("Skipping %s / %s / %s: target has no valid samples", process_type, material, target)
                continue
            all_results.extend(
                fit_models_for_target(
                    group,
                    material=material,
                    target=target,
                    feature_columns=feature_columns,
                    random_seed=random_seed,
                    cv_max_folds=cv_max_folds,
                    logger=logger,
                    process_type=process_type,
                )
            )

    performance = summarize_performance(all_results)
    performance.to_csv(dirs["outputs"] / "model_performance_summary.csv", index=False, encoding="utf-8-sig")
    prediction_results = pd.concat([r.predictions for r in all_results], ignore_index=True) if all_results else pd.DataFrame()
    prediction_results.to_csv(dirs["outputs"] / "prediction_results.csv", index=False, encoding="utf-8-sig")
    plot_pred_vs_true(prediction_results, dirs["figures"])

    best_models = select_best_models(all_results)
    importance = build_feature_importance(best_models, all_results, featured, random_seed, logger)
    importance.to_csv(dirs["outputs"] / "feature_importance_summary.csv", index=False, encoding="utf-8-sig")
    plot_feature_importance(importance, dirs["figures"])

    response_curves = build_response_curves(best_models, featured)
    response_curves.to_csv(dirs["outputs"] / "response_curves.csv", index=False, encoding="utf-8-sig")
    plot_response_curve(response_curves, dirs["figures"])

    recommendations, candidate_maps = recommend_bo(featured, all_results, config, logger)
    if recommendations.empty:
        recommendations = pd.DataFrame(columns=BO_COLUMNS)
    recommendations.to_csv(dirs["outputs"] / "bo_recommendations.csv", index=False, encoding="utf-8-sig")
    plot_bo_maps(recommendations, candidate_maps, dirs["figures"])

    generate_modeling_report(
        dirs["outputs"] / "modeling_report.md",
        unified=unified,
        quality=quality,
        performance=performance,
        best_models=best_models,
        importance=importance,
        recommendations=recommendations,
    )
    logger.info("Workflow complete")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Ultrafast laser process-quality modeling workflow")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init-task", help="Initialize an interactive BO task")
    init_parser.add_argument("--config", default="config.yaml")
    init_parser.add_argument("--process-type", default="milling", choices=["milling", "cutting"])
    init_parser.add_argument("--material", required=True)
    init_parser.add_argument("--objective", required=True, choices=["quality_first", "efficiency_first", "balanced"])
    init_parser.add_argument("--target-depth", type=float)
    init_parser.add_argument("--depth-min", type=float)
    init_parser.add_argument("--sa-max", type=float)

    rec_parser = subparsers.add_parser("recommend", help="Recommend parameters for an existing task")
    rec_parser.add_argument("--config", default="config.yaml")
    rec_parser.add_argument("--task-id")
    rec_parser.add_argument("--process-type", default="milling", choices=["milling", "cutting"])
    rec_parser.add_argument("--material")
    rec_parser.add_argument("--objective", choices=["quality_first", "efficiency_first", "balanced"])
    rec_parser.add_argument("--type", default="balanced", choices=["exploitation", "exploration", "balanced"])

    fb_parser = subparsers.add_parser("feedback", help="Submit feedback for a task iteration")
    fb_parser.add_argument("--task-id")
    fb_parser.add_argument("--feedback")
    fb_parser.add_argument("--iteration", type=int)
    fb_parser.add_argument("--depth", type=float)
    fb_parser.add_argument("--sa", type=float)
    fb_parser.add_argument("--processing-time", type=float)
    level_choices = ["很小", "较小", "适中", "较大", "很大", "acceptable", "too_large", "too_small", "too_shallow", "too_deep", "too_low", "too_high", "unknown"]
    fb_parser.add_argument("--roughness", default="unknown", choices=level_choices)
    fb_parser.add_argument("--depth-status", default="unknown", choices=level_choices)
    fb_parser.add_argument("--efficiency", default="unknown", choices=level_choices)
    fb_parser.add_argument("--note", default="")

    next_parser = subparsers.add_parser("recommend-next", help="Recommend the next point after feedback")
    next_parser.add_argument("--task-id", required=True)
    next_parser.add_argument("--type", default="balanced", choices=["exploitation", "exploration", "balanced"])

    export_parser = subparsers.add_parser("export-task", help="Export task-specific logs")
    export_parser.add_argument("--task-id", required=True)
    export_parser.add_argument("--output-dir", default="outputs")

    json_parser = subparsers.add_parser("run-json", help="Initialize and recommend from task_request.json")
    json_parser.add_argument("--config", default="config.yaml")
    json_parser.add_argument("--task-request", required=True)

    fb_json_parser = subparsers.add_parser("feedback-json", help="Submit feedback from feedback.json and recommend next")
    fb_json_parser.add_argument("--feedback", required=True)
    return parser.parse_args()


def _task_init_response(state: dict) -> dict:
    """Return the public initialization response."""
    return {
        "task_id": state["task_id"],
        "process_type": state.get("process_type", "milling"),
        "material": state["material"],
        "model_status": state.get("model_status"),
        "objective_mode": state["objective_mode"],
        "available_historical_samples": state["available_historical_samples"],
        "depth_model_available": state["depth_model_available"],
        "roughness_model_available": state["roughness_model_available"],
        "parameter_bounds": state["parameter_bounds"],
        "warnings": state.get("warnings", []),
    }


if __name__ == "__main__":
    args = parse_args()
    try:
        if args.command is None:
            run(args.config)
        elif args.command == "init-task":
            cfg = load_config(args.config)
            cfg["_root"] = str(Path(args.config).resolve().parent)
            state = init_task(
                cfg,
                material=args.material,
                objective_mode=args.objective,
                process_type=args.process_type,
                target_depth_um=args.target_depth,
                depth_min_um=args.depth_min,
                Sa_max_um=args.sa_max,
            )
            save_task_state(state)
            print(json.dumps(_task_init_response(state), ensure_ascii=False, indent=2))
        elif args.command == "recommend":
            if args.task_id:
                state = load_task_state(args.task_id)
            else:
                if not args.material or not args.objective:
                    raise ValueError("recommend requires --task-id or both --material and --objective")
                cfg = load_config(args.config)
                cfg["_root"] = str(Path(args.config).resolve().parent)
                state = init_task(cfg, material=args.material, objective_mode=args.objective, process_type=args.process_type)
            rec = recommend_parameters(state, args.type)
            print(json.dumps(rec, ensure_ascii=False, indent=2))
        elif args.command == "feedback":
            if args.feedback:
                rec = feedback_json(args.feedback)
                print(json.dumps(rec, ensure_ascii=False, indent=2))
                raise SystemExit(0)
            if not args.task_id or args.iteration is None:
                raise ValueError("feedback requires --feedback or both --task-id and --iteration")
            state = load_task_state(args.task_id)
            feedback = {
                "task_id": args.task_id,
                "iteration": args.iteration,
                "measured_result": {
                    "depth_um": args.depth,
                    "Sa_um": args.sa,
                    "processing_time_s": args.processing_time,
                },
                "qualitative_feedback": {
                    "roughness": args.roughness,
                    "depth": args.depth_status,
                    "efficiency": args.efficiency,
                },
                "note": args.note,
            }
            updated = submit_feedback(state, feedback)
            print(json.dumps({"task_id": updated["task_id"], "iteration": args.iteration, "feedback_saved": True}, ensure_ascii=False, indent=2))
        elif args.command == "recommend-next":
            state = load_task_state(args.task_id)
            rec = recommend_next(state, args.type)
            print(json.dumps(rec, ensure_ascii=False, indent=2))
        elif args.command == "export-task":
            state = load_task_state(args.task_id)
            paths = export_task_logs(state, args.output_dir)
            print(json.dumps(paths, ensure_ascii=False, indent=2))
        elif args.command == "run-json":
            cfg = load_config(args.config)
            cfg["_root"] = str(Path(args.config).resolve().parent)
            rec = run_json(args.task_request, cfg)
            print(json.dumps(rec, ensure_ascii=False, indent=2))
        elif args.command == "feedback-json":
            rec = feedback_json(args.feedback)
            print(json.dumps(rec, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"ERROR: {exc}") from exc
