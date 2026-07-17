"""Public entry point for the BioEval experiment-agent."""

from bioeval.data_agent import (
    ExperimentAgentSettings,
    build_arg_parser,
    create_app,
    main,
)

__all__ = ["ExperimentAgentSettings", "build_arg_parser", "create_app", "main"]


if __name__ == "__main__":
    main()
