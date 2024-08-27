"""
Marimba: A Python framework for structuring, managing, processing and FAIR-ising scientific marine image datasets.

This module provides the command-line interface for the Marimba framework. It allows users to import data into
collections, process collections using pipelines, package collections into datasets, and distribute datasets to
various targets.

Imports:
    - logging: Python logging module for generating log messages.
    - pathlib.Path: Class for representing filesystem paths.
    - typing.List: Type hint for a list of elements.
    - typing.Optional: Type hint for an optional value.
    - typer: Library for building CLI applications.
    - rich: Library for rich text and beautiful formatting in the terminal.
    - marimba.core.cli.new: Module for creating new Marimba projects.
    - marimba.core.distribution.bases.DistributionTargetBase: Base class for distribution targets.
    - marimba.core.utils.constants.PROJECT_DIR_HELP: Constant for the help text of the project directory option.
    - marimba.core.utils.log: Module for logging utilities.
    - marimba.core.utils.rich: Module for rich text utilities.
    - marimba.core.wrappers.dataset.DatasetWrapper: Wrapper class for Marimba datasets.
    - marimba.core.wrappers.project.ProjectWrapper: Wrapper class for Marimba projects.

Functions:
    - global_options: Sets global options for the Marimba CLI.
    - import_command: Imports data into a new or existing Marimba collection.
    - package_command: Packages a Marimba collection into a dataset.
    - process_command: Processes a Marimba collection based on a pipeline specification.
    - distribute_command: Distributes a Marimba dataset to a specified target.
    - update_command: Updates (pulls) all Marimba pipelines.
    - install_command: Installs Python dependencies from requirements.txt files defined by a project's pipelines.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional

import typer
from rich import print  # noqa: A004

from marimba.core.cli import delete, new
from marimba.core.distribution.bases import DistributionTargetBase
from marimba.core.utils.constants import PROJECT_DIR_HELP, Operation
from marimba.core.utils.log import LogLevel, get_logger, get_rich_handler
from marimba.core.utils.map import NetworkConnectionError
from marimba.core.utils.rich import error_panel, format_entity, success_panel
from marimba.core.wrappers.dataset import DatasetWrapper
from marimba.core.wrappers.project import ProjectWrapper

__author__ = "Marimba Development Team"
__credits__ = [
    "Chris Jackett <chris.jackett@csiro.au>",
    "Kevin Barnard <kbarnard@mbari.org>",
    "Nick Mortimer <nick.mortimer@csiro.au>",
    "David Webb <david.webb@csiro.au>",
    "Aaron Tyndall <aaron.tyndall@csiro.au>",
    "Franzis Althaus <franzis.althaus@csiro.au>",
    "Bec Gorton <bec.gorton@csiro.au>",
    "Ben Scoulding <ben.scoulding@csiro.au>",
]
__license__ = "CC BY-SA 4.0"
__version__ = "0.4.0"
__maintainer__ = "Chris Jackett"
__email__ = "chris.jackett@csiro.au"
__status__ = "Development"


marimba_cli = typer.Typer(
    name="Marimba",
    help="""Marimba\n
        A Python framework for structuring, managing, processing and FAIR-ising scientific marine image datasets.""",
    short_help="Marimba",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

marimba_cli.add_typer(new.app, name="new")
marimba_cli.add_typer(delete.app, name="delete")

logger = get_logger(__name__)


@marimba_cli.callback()
def global_options(
    level: LogLevel = typer.Option(LogLevel.WARNING, help="Logging level."),
) -> None:
    """
    Global options for Marimba CLI.
    """
    get_rich_handler().setLevel(logging.getLevelName(level.value))
    logger.info(f"Initialised Marimba CLI v{__version__}")


@marimba_cli.command("import")
def import_command(
    collection_name: str = typer.Argument(..., help="Marimba collection name for targeted processing."),
    source_paths: List[Path] = typer.Argument(..., help="Paths to source files/directories to provide for import."),
    parent_collection_name: Optional[str] = typer.Option(
        None, help="Name of the parent collection. If unspecified, use the last collection."
    ),
    project_dir: Optional[Path] = typer.Option(None, help=PROJECT_DIR_HELP),
    overwrite: bool = typer.Option(False, help="Overwrite an existing collection with the same name."),
    config: str = typer.Option(
        None, help="A custom configuration in JSON format to be merged with the prompted collection configuration."
    ),
    extra: List[str] = typer.Option([], help="Extra key-value pass-through arguments."),
    dry_run: bool = typer.Option(
        False, help="Execute the command and print logging to the terminal, but do not change any files."
    ),
) -> None:
    """
    Import data in a source directory into a new or existing Marimba collection.
    """
    start_time = time.time()

    try:
        config_dict = json.loads(config) if config else {}
    except json.JSONDecodeError as e:
        error_message = f"Error parsing configuration JSON: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()

    project_dir = new.find_project_dir_or_exit(project_dir)
    project_wrapper = ProjectWrapper(project_dir, dry_run=dry_run)
    get_rich_handler().set_dry_run(dry_run)

    # Get the collection (create if appropriate)
    collection_wrapper = project_wrapper.collection_wrappers.get(collection_name, None)
    if collection_wrapper is None:
        try:
            collection_config = project_wrapper.prompt_collection_config(
                parent_collection_name=parent_collection_name,
                config=config_dict,
            )
            project_wrapper.create_collection(collection_name, collection_config)
        except ProjectWrapper.InvalidNameError as e:
            error_message = f"Invalid collection name: {e}"
            logger.error(error_message)
            print(error_panel(error_message))
            raise typer.Exit()
    elif not overwrite:
        error_message = f"Collection {collection_name} already exists, and the overwrite flag is not set."
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()

    # Run the import
    try:
        project_wrapper.run_import(collection_name, source_paths, extra_args=extra)
    except Exception as e:
        error_message = f"Error during import: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()

    pretty_source_paths = "\n".join([f"  - {source_path.resolve().absolute()}" for source_path in source_paths])
    elapsed_time = time.time() - start_time
    print(
        success_panel(
            f'Imported data into collection "{format_entity(collection_name)}" from the following source paths in '
            f"{elapsed_time:.2f} seconds:\n{pretty_source_paths}"
        )
    )


@marimba_cli.command("package")
def package_command(
    dataset_name: str = typer.Argument(..., help="Marimba dataset name."),
    # pipeline_name: str = typer.Argument(..., help="Marimba pipeline name to package."),
    collection_names: Optional[List[str]] = typer.Argument(
        None,
        help="Marimba collection names to package. If none are specified, "
        "all collections will be packaged together.",
    ),
    project_dir: Optional[Path] = typer.Option(None, help=PROJECT_DIR_HELP),
    operation: Operation = typer.Option(Operation.copy, help="Operation to perform: copy, move, or link"),
    version: Optional[str] = typer.Option("1.0", help="Version of the packaged dataset."),
    contact_name: Optional[str] = typer.Option(None, help="Full name of the contact person for the packaged dataset."),
    contact_email: Optional[str] = typer.Option(
        None, help="Email address of the contact person for the packaged dataset."
    ),
    extra: List[str] = typer.Option([], help="Extra key-value pass-through arguments."),
    dry_run: bool = typer.Option(
        False, help="Execute the command and print logging to the terminal, but do not change any files."
    ),
) -> None:
    """
    Package up a Marimba collection ready for distribution.
    """
    start_time = time.time()

    project_dir = new.find_project_dir_or_exit(project_dir)
    project_wrapper = ProjectWrapper(project_dir, dry_run=dry_run)
    get_rich_handler().set_dry_run(dry_run)

    if not collection_names:  # If no collection names are specified, package all collections
        collection_names = list(project_wrapper.collection_wrappers.keys())

    try:
        # Compose the dataset
        dataset_mapping = project_wrapper.compose(dataset_name, collection_names, extra)

        # Package it
        dataset_wrapper = project_wrapper.create_dataset(
            dataset_name,
            dataset_mapping,
            operation=operation,
            version=version,
            contact_name=contact_name,
            contact_email=contact_email,
        )
    except ProjectWrapper.CompositionError as e:
        logger.error(e)
        print(error_panel(str(e)))
        raise typer.Exit()
    except ProjectWrapper.NoSuchPipelineError as e:
        error_message = f"No such pipeline: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except ProjectWrapper.NoSuchCollectionError as e:
        error_message = f"No such collection: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except DatasetWrapper.ManifestError as e:
        error_message = f"Dataset is inconsistent with manifest at {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except FileExistsError as e:
        error_message = f"Dataset already exists: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except Exception as e:
        logger.error(e)
        print(error_panel(f"Could not package collection: {e}"))
        raise typer.Exit()

    elapsed_time = time.time() - start_time
    print(
        success_panel(
            f'Packaged dataset "{format_entity(dataset_name)}" at {dataset_wrapper.root_dir} in '
            f"{elapsed_time:.2f} seconds"
        )
    )


@marimba_cli.command("process")
def process_command(
    pipeline_name: Optional[str] = typer.Option(None, help="Marimba pipeline name for targeted processing."),
    collection_name: Optional[str] = typer.Option(None, help="Marimba collection name for targeted processing."),
    project_dir: Optional[Path] = typer.Option(None, help=PROJECT_DIR_HELP),
    extra: List[str] = typer.Option([], help="Extra key-value pass-through arguments."),
    dry_run: bool = typer.Option(
        False, help="Execute the command and print logging to the terminal, but do not change any files."
    ),
) -> None:
    """
    Process the Marimba collection based on the pipeline specification.
    """
    start_time = time.time()

    project_dir = new.find_project_dir_or_exit(project_dir)
    project_wrapper = ProjectWrapper(project_dir, dry_run=dry_run)
    get_rich_handler().set_dry_run(dry_run)

    # Run the processing
    try:
        project_wrapper.run_process(pipeline_name, collection_name, extra)
    except NetworkConnectionError as e:
        error_message = f"No internet connection: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except Exception as e:
        error_message = f"Error during processing: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()

    if pipeline_name is None:
        pipeline_names = list(project_wrapper.pipeline_wrappers.keys())
    else:
        pipeline_names = [pipeline_name]

    if collection_name is None:
        collection_names = list(project_wrapper.collection_wrappers.keys())
    else:
        collection_names = [collection_name]

    pretty_pipelines = ", ".join(f'"{str(p)}"' for p in pipeline_names)
    pretty_collections = ", ".join(f'"{str(c)}"' for c in collection_names)
    pipeline_label = "pipeline" if len(pipeline_names) == 1 else "pipelines"
    collection_label = "collection" if len(collection_names) == 1 else "collections"

    elapsed_time = time.time() - start_time
    print(
        success_panel(
            f"Processed data for {pipeline_label} {pretty_pipelines} and {collection_label} {pretty_collections} in "
            f"{elapsed_time:.2f} seconds"
        )
    )


@marimba_cli.command("distribute")
def distribute_command(
    dataset_name: str = typer.Argument(..., help="Marimba dataset name."),
    target_name: str = typer.Argument(..., help="Marimba distribution target name."),
    project_dir: Optional[Path] = typer.Option(None, help=PROJECT_DIR_HELP),
    dry_run: bool = typer.Option(
        False, help="Execute the command and print logging to the terminal, but do not change any files."
    ),
) -> None:
    """
    Distribute a Marimba dataset.
    """
    start_time = time.time()

    project_dir = new.find_project_dir_or_exit(project_dir)
    project_wrapper = ProjectWrapper(project_dir, dry_run=dry_run)
    get_rich_handler().set_dry_run(dry_run)

    try:
        project_wrapper.distribute(dataset_name, target_name)
    except ProjectWrapper.NoSuchDatasetError as e:
        error_message = f"No such dataset: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except ProjectWrapper.NoSuchTargetError as e:
        error_message = f"No such target: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except DatasetWrapper.ManifestError as e:
        error_message = f"Dataset is inconsistent with manifest at {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except DistributionTargetBase.DistributionError as e:
        error_message = f"Could not distribute dataset: {e}"
        logger.error(error_message)
        print(error_panel(error_message))
        raise typer.Exit()
    except Exception as e:
        logger.error(e)
        print(error_panel(f"Could not distribute dataset: {e}"))
        raise typer.Exit()

    elapsed_time = time.time() - start_time
    print(success_panel(f"Successfully distributed dataset {dataset_name} in {elapsed_time:.2f} seconds"))


@marimba_cli.command("update")
def update_command(project_dir: Optional[Path] = typer.Option(None, help=PROJECT_DIR_HELP)) -> None:
    """
    Update (pull) all Marimba pipelines.
    """
    project_dir = new.find_project_dir_or_exit(project_dir)
    project_wrapper = ProjectWrapper(project_dir)

    try:
        project_wrapper.update_pipelines()
    except Exception as e:
        logger.error(e)
        print(error_panel(f"Could not update pipelines: {e}"))
        raise typer.Exit()


@marimba_cli.command("install")
def install_command(project_dir: Optional[Path] = typer.Option(None, help=PROJECT_DIR_HELP)) -> None:
    """
    Install Python dependencies from requirements.txt files defined by a project's pipelines.
    """
    project_dir = new.find_project_dir_or_exit(project_dir)
    project_wrapper = ProjectWrapper(project_dir)

    try:
        project_wrapper.install_pipelines()
    except Exception as e:
        logger.error(e)
        print(error_panel(f"Could not install pipelines: {e}"))
        raise typer.Exit()


if __name__ == "__main__":
    marimba_cli()