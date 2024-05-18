"""
Marimba Core Pipeline Wrapper Module.

This module provides the PipelineWrapper class for managing pipeline directories, including creation, configuration,
dependency installation, and instance management.

The PipelineWrapper class allows for creating a new pipeline directory from a remote git repository, loading and
saving pipeline configurations, and retrieving instances of the pipeline implementation. It also provides functionality
for updating the pipeline repository and installing pipeline dependencies.

Imports:
    - logging: Python logging module for logging messages.
    - shutil: High-level operations on files and collections of files.
    - subprocess: Subprocess management module for running external commands.
    - sys: System-specific parameters and functions.
    - importlib.util: Utility functions for importing modules.
    - pathlib.Path: Object-oriented filesystem paths.
    - typing: Support for type hints.
    - git.Repo: GitPython library for interacting with Git repositories.
    - marimba.core.pipeline.BasePipeline: Base class for pipeline implementations.
    - marimba.core.utils.config: Utility functions for loading and saving configuration files.
    - marimba.core.utils.log.LogMixin: Mixin class for adding logging functionality.
    - marimba.core.utils.log.get_file_handler: Function for creating a file handler for logging.

Classes:
    - PipelineWrapper: Pipeline directory wrapper class for managing pipeline directories.
        - InvalidStructureError: Exception raised when the project file structure is invalid.
        - InstallError: Exception raised when there is an error installing pipeline dependencies.
"""


import logging
import shutil
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, Dict, Optional, Type, Union

from git import Repo

from marimba.core.pipeline import BasePipeline
from marimba.core.utils.config import load_config, save_config
from marimba.core.utils.log import LogMixin, get_file_handler


class PipelineWrapper(LogMixin):
    """
    Pipeline directory wrapper.
    """

    class InvalidStructureError(Exception):
        """
        Raised when the project file structure is invalid.
        """

    class InstallError(Exception):
        """
        Raised when there is an error installing pipeline dependencies.
        """

    def __init__(self, root_dir: Union[str, Path], dry_run: bool = False):
        """
        Initialise the class instance.

        Args:
            root_dir: A string or Path object representing the root directory.
            dry_run: A boolean indicating whether the method should be executed in a dry run mode.
        """
        self._root_dir = Path(root_dir)
        self._dry_run = dry_run

        self._file_handler: Optional[logging.FileHandler] = None
        self._pipeline_class: Optional[Type[BasePipeline]] = None

        self._check_file_structure()
        self._setup_logging()

    @property
    def root_dir(self) -> Path:
        """
        The root directory of the pipeline.
        """
        return self._root_dir

    @property
    def repo_dir(self) -> Path:
        """
        The repository directory of the pipeline.
        """
        return self.root_dir / "repo"

    @property
    def config_path(self) -> Path:
        """
        The path to the pipeline configuration file.
        """
        return self.root_dir / "pipeline.yml"

    @property
    def requirements_path(self) -> Path:
        """
        The path to the pipeline requirements file.
        """
        return self.repo_dir / "requirements.txt"

    @property
    def log_path(self) -> Path:
        """
        The path to the project log file.
        """
        return self._root_dir / f"{self.name}.log"

    @property
    def name(self) -> str:
        """
        The name of the pipeline.
        """
        return self.root_dir.name

    @property
    def dry_run(self) -> bool:
        """
        Whether the pipeline should run in dry-run mode.
        """
        return self._dry_run

    def _check_file_structure(self) -> None:
        """
        Check that the pipeline file structure is valid. If not, raise an InvalidStructureError with details.

        Raises:
            PipelineDirectory.InvalidStructureError: If the pipeline file structure is invalid.
        """

        def check_dir_exists(path: Path) -> None:
            if not path.is_dir():
                raise PipelineWrapper.InvalidStructureError(f'"{path}" does not exist or is not a directory.')

        def check_file_exists(path: Path) -> None:
            if not path.is_file():
                raise PipelineWrapper.InvalidStructureError(f'"{path}" does not exist or is not a file.')

        check_dir_exists(self.root_dir)
        check_dir_exists(self.repo_dir)
        check_file_exists(self.config_path)

    def _setup_logging(self) -> None:
        """
        Set up logging. Create file handler for this instance that writes to `pipeline.log`.
        """
        # Create a file handler for this instance
        self._file_handler = get_file_handler(self.root_dir, self.name, False, level=logging.DEBUG)

        # Add the file handler to the logger
        self.logger.addHandler(self._file_handler)

    @classmethod
    def create(cls, root_dir: Union[str, Path], url: str, dry_run: bool = False) -> "PipelineWrapper":
        """
        Create a new pipeline directory from a remote git repository.

        Args:
            root_dir: The root directory of the pipeline.
            url: The URL of the pipeline implementation git repository.
            dry_run: Whether to run in dry-run mode.

        Raises:
            FileExistsError: If the pipeline root directory already exists.
        """
        root_dir = Path(root_dir)

        # Check that the root directory doesn't already exist
        if root_dir.exists():
            raise FileExistsError(f'Pipeline root directory "{root_dir}" already exists.')

        # Create the pipeline root directory
        root_dir.mkdir(parents=True)

        # Clone the pipeline repository
        repo_dir = root_dir / "repo"
        Repo.clone_from(url, repo_dir)

        # Create the pipeline configuration file (initialize as empty)
        config_path = root_dir / "pipeline.yml"
        save_config(config_path, {})

        return cls(root_dir, dry_run=dry_run)

    def load_config(self) -> Dict[str, Any]:
        """
        Load the pipeline configuration.

        Returns:
            The pipeline configuration.
        """
        return load_config(self.config_path)

    def save_config(self, config: Optional[Dict[Any, Any]]) -> None:
        """
        Save the pipeline configuration.

        Args:
            config: The pipeline configuration.
        """
        if config:
            save_config(self.config_path, config)

    def get_instance(self) -> BasePipeline:
        """
        Get an instance of the pipeline implementation.

        Injects the pipeline configuration and logger into the instance.

        Returns:
            The pipeline instance.

        Raises:
            FileNotFoundError:
                If the pipeline implementation file cannot be found, or if there are multiple pipeline implementation
                files.
            ImportError: If the pipeline implementation file cannot be imported.
        """
        # Get the pipeline class
        pipeline_class = self.get_pipeline_class()

        if pipeline_class is None:
            raise ImportError("Pipeline class has not been set or could not be found.")

        # Create an instance of the pipeline
        pipeline_instance = pipeline_class(self.repo_dir, config=self.load_config(), dry_run=self.dry_run)

        # Set up pipeline file logging if _file_handler is initialized
        if self._file_handler is not None:
            pipeline_instance.logger.addHandler(self._file_handler)

        return pipeline_instance

    def get_pipeline_class(self) -> Optional[Type[BasePipeline]]:
        """
        Get the pipeline class.

        Lazy-loaded and cached. Automatically scans the repository for a pipeline implementation.

        Returns:
            The pipeline class.

        Raises:
            FileNotFoundError:
                If the pipeline implementation file cannot be found, or if there are multiple pipeline implementation
                files.
            ImportError: If the pipeline implementation file cannot be imported.
        """
        if self._pipeline_class is None:
            # Find files that end with .pipeline.py in the repository
            pipeline_module_paths = list(self.repo_dir.glob("**/*.pipeline.py"))

            # Ensure there is one result
            if len(pipeline_module_paths) == 0:
                raise FileNotFoundError(f'No pipeline implementation found in "{self.repo_dir}".')

            if len(pipeline_module_paths) > 1:
                raise FileNotFoundError(
                    f'Multiple pipeline implementations found in "{self.repo_dir}": {pipeline_module_paths}.'
                )
            pipeline_module_path = pipeline_module_paths[0]

            pipeline_module_name = pipeline_module_path.stem
            pipeline_module_spec = spec_from_file_location(
                pipeline_module_name,
                str(pipeline_module_path.absolute()),
            )

            if pipeline_module_spec is None:
                raise ImportError(f"Could not load spec for {pipeline_module_name} from {pipeline_module_path}")

            # Create the pipeline module
            pipeline_module = module_from_spec(pipeline_module_spec)

            # Enable repo-relative imports by temporarily adding the repository directory to the module search path
            sys.path.insert(0, str(self.repo_dir.absolute()))

            # Ensure that loader is not None before executing the module
            if pipeline_module_spec.loader is None:
                raise ImportError(f"Could not find loader for {pipeline_module_name} from {pipeline_module_path}")

            # Execute it
            pipeline_module_spec.loader.exec_module(pipeline_module)

            # Remove the repository directory from the module search path to avoid conflicts
            sys.path.pop(0)

            # Find any BasePipeline implementations
            for _, obj in pipeline_module.__dict__.items():
                if isinstance(obj, type) and issubclass(obj, BasePipeline) and obj is not BasePipeline:
                    self._pipeline_class = obj
                    break

        return self._pipeline_class

    def update(self) -> None:
        """
        Update the pipeline repository by issuing a git pull.
        """
        repo = Repo(self.repo_dir)
        repo.remotes.origin.pull()

    def install(self) -> None:
        """
        Install the pipeline dependencies as provided in a requirements.txt file, if present.

        Raises:
            PipelineWrapper.InstallError: If there is an error installing pipeline dependencies.
        """
        if self.requirements_path.is_file():
            self.logger.info(f"Installing pipeline dependencies from {self.requirements_path}...")
            try:
                # Ensure the requirements path is an absolute path and exists
                requirements_path = str(self.requirements_path.absolute())
                if not Path(requirements_path).is_file():
                    raise PipelineWrapper.InstallError(f"Requirements file not found: {requirements_path}")

                # Find the full path to the pip executable
                pip_path = shutil.which("pip")
                if pip_path is None:
                    raise PipelineWrapper.InstallError("pip executable not found in PATH")

                with subprocess.Popen(
                    [pip_path, "install", "--no-input", "-r", requirements_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                ) as process:
                    output, error = process.communicate()
                    if output:
                        self.logger.debug(output.decode("utf-8"))
                    if error:
                        self.logger.warning(error.decode("utf-8"))

                    if process.returncode != 0:
                        raise PipelineWrapper.InstallError(
                            f"pip install had a non-zero return code: {process.returncode}"
                        )

                self.logger.info("Pipeline dependencies installed successfully.")
            except Exception as e:
                self.logger.error(f"Error installing pipeline dependencies: {e}")
                raise PipelineWrapper.InstallError from e
        else:
            self.logger.error(f"Requirements file does not exist: {self.requirements_path}")
            raise PipelineWrapper.InstallError(f"Requirements file does not exist: {self.requirements_path}")
