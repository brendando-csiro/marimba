import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ifdo import iFDO

from marimba.utils.log import LogMixin, get_file_handler, get_logger
from marimba.utils.rich import MARIMBA
from marimba.wrappers.deployment import DeploymentWrapper
from marimba.wrappers.package import PackageWrapper
from marimba.wrappers.pipeline import PipelineWrapper

logger = get_logger(__name__)


def get_base_templates_path() -> Path:
    base_templates_path = Path(__file__).parent.parent.parent / "templates"
    logger.info(f'Setting {MARIMBA} base templates path to: "{base_templates_path}"')
    return base_templates_path


def check_template_exists(base_templates_path: Union[str, Path], template_name: str, template_type: str) -> Path:
    base_templates_path = Path(base_templates_path)
    logger.info(f"Checking that the provided {MARIMBA} [light_pink3]{template_type}[/light_pink3] template exists...")
    template_path = base_templates_path / template_name / template_type

    if template_path.is_dir():
        logger.info(f"{MARIMBA} [light_pink3]{template_type}[/light_pink3] template [orchid1]{Path(template_name) / template_type}[/orchid1] exists!")
    else:
        error_message = f"The provided [light_pink3]{template_type}[/light_pink3] template name [orchid1]{Path(template_name) / template_type}[/orchid1] does not exists at {template_path}"
        logger.error(error_message)
        # print(
        #     Panel(
        #         error_message,
        #         title="Error",
        #         title_align="left",
        #         border_style="red",
        #     )
        # )
        # raise typer.Exit()

    return template_path


def get_merged_keyword_args(kwargs: dict, extra_args: list, logger: logging.Logger) -> dict:
    """
    Merge any extra key-value arguments with other keyword arguments.

    Args:
        kwargs: The keyword arguments to merge with.
        extra_args: A list of extra key-value arguments to merge.
        logger: A logger object to log any warnings.

    Returns:
        A dictionary containing the merged keyword arguments.
    """
    extra_dict = {}
    if extra_args:
        for arg in extra_args:
            # Attempt to split the argument into a key and a value
            parts = arg.split("=")
            if len(parts) == 2:
                key, value = parts
                extra_dict[key] = value
            else:
                logger.warning(f'Invalid extra argument provided: "{arg}"')

    return {**kwargs, **extra_dict}


class ProjectWrapper(LogMixin):
    """
    MarImBA project directory wrapper. Provides methods for interacting with the project.

    To create a new project, use the `create` method:
    ```python
    project_wrapper = ProjectWrapper.create("my_project")
    ```

    To wrap an existing project, use the constructor:
    ```python
    project_wrapper = ProjectWrapper("my_project")
    ```
    """

    class InvalidStructureError(Exception):
        """
        Raised when the project file structure is invalid.
        """

        pass

    class CreatePipelineError(Exception):
        """
        Raised when an instrument cannot be created.
        """

        pass

    class CreateDeploymentError(Exception):
        """
        Raised when a deployment cannot be created.
        """

        pass

    class RunCommandError(Exception):
        """
        Raised when a command cannot be run.
        """

        pass

    class NoSuchPipelineError(Exception):
        """
        Raised when an instrument does not exist in the project.
        """

        pass

    class NoSuchDeploymentError(Exception):
        """
        Raised when a deployment does not exist in the project.
        """

        pass

    def __init__(self, root_dir: Union[str, Path]):
        super().__init__()

        self._root_dir = Path(root_dir)

        self._pipeline_dir = self._root_dir / "pipelines"
        self._deployments_dir = self._root_dir / "deployments"
        self._marimba_dir = self._root_dir / ".marimba"

        self._pipeline_wrappers = {}  # instrument name -> InstrumentWrapper instance
        self._deployment_wrappers = {}  # deployment name -> DeploymentWrapper instance

        self._check_file_structure()
        self._setup_logging()

        self._load_pipeline()
        self._load_deployments()

    @classmethod
    def create(cls, root_dir: Union[str, Path]) -> "ProjectWrapper":
        """
        Create a project from a root directory.

        Args:
            root_dir: The root directory of the project.

        Returns:
            A project.

        Raises:
            FileExistsError: If the root directory already exists.
        """
        # Define the folder structure
        root_dir = Path(root_dir)
        pipeline_dir = root_dir / "pipelines"
        deployments_dir = root_dir / "deployments"
        marimba_dir = root_dir / ".marimba"

        # Check that the root directory doesn't already exist
        if root_dir.exists():
            raise FileExistsError(f'"{root_dir}" already exists.')

        # Create the folder structure
        root_dir.mkdir(parents=True)
        pipeline_dir.mkdir()
        deployments_dir.mkdir()
        marimba_dir.mkdir()

        return cls(root_dir)

    def _check_file_structure(self):
        """
        Check that the project file structure is valid. If not, raise an InvalidStructureError with details.

        Raises:
            ProjectWrapper.InvalidStructureError: If the project file structure is invalid.
        """

        def check_dir_exists(path: Path):
            if not path.is_dir():
                raise ProjectWrapper.InvalidStructureError(f'"{path}" does not exist or is not a directory.')

        check_dir_exists(self._root_dir)
        check_dir_exists(self._pipeline_dir)
        check_dir_exists(self._deployments_dir)
        check_dir_exists(self._marimba_dir)

    def _setup_logging(self):
        """
        Set up logging. Create file handler for this instance that writes to `project.log`.
        """
        # Create a file handler for this instance
        file_handler = get_file_handler(self.root_dir, self.name, False, level=logging.DEBUG)

        # Add the file handler to the logger
        self.logger.addHandler(file_handler)

    def _load_pipeline(self):
        """
        Load instrument wrappers from the `instruments` directory.

        Populates the `_instrument_wrappers` dictionary with `InstrumentWrapper` instances.

        Raises:
            InstrumentWrapper.InvalidStructureError: If the instrument directory structure is invalid.
        """
        pipeline_dirs = filter(lambda p: p.is_dir(), self._pipeline_dir.iterdir())

        self._pipeline_wrappers.clear()
        for pipeline_dir in pipeline_dirs:
            self._pipeline_wrappers[pipeline_dir.name] = PipelineWrapper(pipeline_dir)

    def _load_deployments(self):
        """
        Load deployment instances from the `deployments` directory.

        Populates the `_deployment_wrappers` dictionary with `DeploymentWrapper` instances.

        Raises:
            Deployment.InvalidStructureError: If the deployment directory structure is invalid.
        """

        deployment_dirs = filter(lambda p: p.is_dir(), self._deployments_dir.iterdir())

        self._deployment_wrappers.clear()
        for deployment_dir in deployment_dirs:
            self._deployment_wrappers[deployment_dir.name] = DeploymentWrapper(deployment_dir)

    def create_pipeline(self, name: str, url: str) -> PipelineWrapper:
        """
        Create a new instrument.

        Args:
            name: The name of the instrument.
            url: URL of the instrument git repository.

        Returns:
            The instrument directory wrapper.

        Raises:
            ProjectWrapper.CreateInstrumentError: If the instrument cannot be created.
        """
        self.logger.debug(f'Creating instrument "{name}" from {url}')

        # Check that an instrument with the same name doesn't already exist
        pipeline_dir = self._pipeline_dir / name
        if pipeline_dir.exists():
            raise ProjectWrapper.CreatePipelineError(f'An instrument with the name "{name}" already exists.')

        # Create the instrument directory
        pipeline_wrapper = PipelineWrapper.create(pipeline_dir, url)

        # Reload the instruments
        # TODO: Do we need to do this every time?
        self._load_pipeline()

        return pipeline_wrapper

    def create_deployment(self, name: str, parent: Optional[str] = None) -> DeploymentWrapper:
        """
        Create a new deployment.

        Args:
            name: The name of the deployment.
            parent: The name of the parent deployment.

        Returns:
            The deployment directory wrapper.

        Raises:
            ProjectWrapper.CreateDeploymentError: If the deployment cannot be created.
        """
        self.logger.debug(f'Creating deployment "{name}"')

        # Check that a deployment with the same name doesn't already exist
        deployment_dir = self.deployments_dir / name
        if deployment_dir.exists():
            raise ProjectWrapper.CreateDeploymentError(f'A deployment with the name "{name}" already exists.')
        if parent is not None and parent not in self._deployment_wrappers:
            raise ProjectWrapper.CreateDeploymentError(f'The parent deployment "{parent}" does not exist.')

        if parent is None:
            # TODO: Assign parent to the last deployment, if there is one
            pass

        # TODO: Use the parent deployment to populate the default deployment config

        # Create the deployment directory
        deployment_wrapper = DeploymentWrapper.create(deployment_dir, {})

        # Create the per-instrument directories
        for pipeline_name in self._pipeline_wrappers:
            # TODO: Direct this from the instrument implementation?
            deployment_wrapper.get_pipeline_data_dir(pipeline_name).mkdir()

        # Reload the deployments
        # TODO: Do we need to do this every time?
        self._load_deployments()

        return deployment_wrapper

    def run_command(
        self,
        command_name: str,
        pipeline_name: Optional[str] = None,
        deployment_name: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        **kwargs: dict,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Run a command within the project.

        By default, this will run the command for all instruments and deployments in the project.
        If an instrument name is provided, it will run the command for all deployments of that instrument.
        If a deployment name is provided, it will run the command for that deployment only.
        These can be combined to run the command for a specific deployment of a specific instrument.

        Args:
            command_name: The name of the command to run.
            instrument_name: The name of the instrument to run the command for.
            deployment_name: The name of the deployment to run the command for.
            extra_args: Any extra arguments to pass to the command.
            kwargs: Any keyword arguments to pass to the command.

        Returns:
            A dictionary containing the results of the command for each deployment: {deployment_name: {instrument_name: result}}.

        Raises:
            ProjectWrapper.RunCommandError: If the command cannot be run.
        """
        merged_kwargs = get_merged_keyword_args(kwargs, extra_args, self.logger)

        if pipeline_name is not None:
            pipeline_wrapper = self._pipeline_wrappers.get(pipeline_name, None)
            if pipeline_wrapper is None:
                raise ProjectWrapper.RunCommandError(f'Instrument "{pipeline_name}" does not exist within the project.')

        if deployment_name is not None:
            deployment_wrapper = self._deployment_wrappers.get(deployment_name, None)
            if deployment_wrapper is None:
                raise ProjectWrapper.RunCommandError(f'Deployment "{deployment_name}" does not exist within the project.')

        # Select the instruments and deployments to run the command for
        pipeline_wrappers_to_run = {pipeline_name: pipeline_wrapper} if pipeline_name is not None else self._pipeline_wrappers
        deployment_wrappers_to_run = {deployment_name: deployment_wrapper} if deployment_name is not None else self._deployment_wrappers

        # Load instrument instances
        pipeline_to_run = {pipeline_name: pipeline_wrapper.load_pipeline() for pipeline_name, pipeline_wrapper in pipeline_wrappers_to_run.items()}

        # Check that the command exists for all instruments
        for run_pipeline_name, run_pipeline in pipeline_to_run.items():
            if not hasattr(run_pipeline, command_name):
                raise ProjectWrapper.RunCommandError(f'Command "{command_name}" does not exist for instrument "{run_pipeline_name}".')

        # Invoke the command for each instrument and deployment
        results_by_deployment = {}
        for run_deployment_name, run_deployment_wrapper in deployment_wrappers_to_run.items():
            results_by_pipeline = {}
            for run_pipeline_name, run_pipeline in pipeline_to_run.items():
                # Get the instrument-specific data directory and config
                pipeline_deployment_data_dir = run_deployment_wrapper.get_pipeline_data_dir(run_pipeline_name)
                pipeline_deployment_config = run_deployment_wrapper.load_config()

                # Call the method
                method = getattr(run_pipeline, command_name)
                results_by_pipeline[run_pipeline_name] = method(pipeline_deployment_data_dir, pipeline_deployment_config, **merged_kwargs)

            results_by_deployment[run_deployment_name] = results_by_pipeline

        return results_by_deployment

    def compose(
        self, pipeline_name: str, deployment_names: List[str], extra_args: Optional[List[str]] = None, **kwargs: dict
    ) -> Tuple[iFDO, Dict[Path, Path]]:
        """
        Compose a dataset for a given instrument.

        Args:
            instrument_name: The name of the instrument to use.
            deployment_names: The names of the deployments to compose.
            extra_args: Any extra CLI arguments to pass to the command.
            kwargs: Any keyword arguments to pass to the command.

        Returns:
            A tuple containing the iFDO and a dictionary of deployment data file paths to the desired relative dataset paths.

        Raises:
            ProjectWrapper.NoSuchInstrumentError: If the instrument does not exist in the project.
            ProjectWrapper.NoSuchDeploymentError: If a deployment does not exist in the project.
        """
        merged_kwargs = get_merged_keyword_args(kwargs, extra_args, self.logger)

        # Get the instrument wrapper
        pipeline_wrapper = self.pipeline_wrappers.get(pipeline_name, None)
        if pipeline_wrapper is None:
            raise ProjectWrapper.NoSuchPipelineError(pipeline_name)

        # Get the instrument instance
        pipeline = pipeline_wrapper.load_pipeline()

        # Get the deployment wrappers
        deployment_wrappers: List[DeploymentWrapper] = []
        for deployment_name in deployment_names:
            deployment_wrapper = self.deployment_wrappers.get(deployment_name, None)
            if deployment_wrapper is None:
                raise ProjectWrapper.NoSuchDeploymentError(deployment_name)
            deployment_wrappers.append(deployment_wrapper)

        # Get the deployment data directories for the instrument
        deployment_data_dirs = [deployment_wrapper.get_pipeline_data_dir(pipeline_name) for deployment_wrapper in deployment_wrappers]

        # Load the deployment configs
        deployment_configs = [deployment_wrapper.load_config() for deployment_wrapper in deployment_wrappers]

        # Compose the dataset
        return pipeline.run_compose(deployment_data_dirs, deployment_configs, **merged_kwargs)

    def package(self, name: str, ifdo: iFDO, path_mapping: Dict[Path, Path], copy: bool = True) -> PackageWrapper:
        """
        Create a MarImBA package from an iFDO and a path mapping.

        Args:
            name: The name of the package.
            ifdo: The iFDO to package.
            path_mapping: A dictionary of paths to relative paths.
            copy: Whether to copy the files (True) or move them (False).

        Returns:
            A package wrapper instance for the created package.

        Raises:
            FileExistsError: If the package root directory already exists.
            PackageWrapper.InvalidPathMappingError: If the path mapping is invalid.
        """
        package_root_dir = self.distribution_dir / name

        # Create the package
        package_wrapper = PackageWrapper.create(package_root_dir, ifdo)

        # Populate it
        package_wrapper.populate(path_mapping, copy=copy)

        return package_wrapper

    def update_pipelines(self):
        """
        Update all instruments in the project.
        """
        for pipeline_name, pipeline_wrapper in self._pipeline_wrappers.items():
            self.logger.info(f'Updating instrument "{pipeline_name}"')
            try:
                pipeline_wrapper.update()
                self.logger.info(f'Successfully updated instrument "{pipeline_name}"')
            except Exception as e:
                self.logger.error(f'Failed to update instrument "{pipeline_name}": {e}')

    @property
    def pipeline_wrappers(self) -> Dict[str, PipelineWrapper]:
        """
        The loaded instrument wrappers in the project.
        """
        return self._pipeline_wrappers

    @property
    def deployment_wrappers(self) -> Dict[str, DeploymentWrapper]:
        """
        The loaded deployment wrappers in the project.
        """
        return self._deployment_wrappers

    @property
    def root_dir(self) -> Path:
        """
        The root directory of the project.
        """
        return self._root_dir

    @property
    def pipeline_dir(self) -> Path:
        """
        The instruments directory of the project.
        """
        return self._pipeline_dir

    @property
    def deployments_dir(self) -> Path:
        """
        The deployments directory of the project.
        """
        return self._deployments_dir

    @property
    def distribution_dir(self) -> Path:
        """
        The path to the distribution directory. Lazy-created on first access.
        """
        distribution_dir = self._root_dir / "dist"
        distribution_dir.mkdir(exist_ok=True)
        return distribution_dir

    @property
    def marimba_dir(self) -> Path:
        """
        The MarImBA directory of the project.
        """
        return self._marimba_dir

    @property
    def name(self) -> str:
        """
        The name of the project.
        """
        return self._root_dir.name

    @property
    def pipelines(self) -> Dict[str, PipelineWrapper]:
        """
        The loaded instruments in the project.
        """
        return self._pipeline_wrappers

    @property
    def deployments(self) -> Dict[str, DeploymentWrapper]:
        """
        The loaded deployments in the project.
        """
        return self._deployment_wrappers
