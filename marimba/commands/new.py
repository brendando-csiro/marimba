import os
from datetime import datetime
from pathlib import Path

import typer
from cookiecutter.main import cookiecutter
from cookiecutter.exceptions import OutputDirExistsException
from rich import print
from rich.panel import Panel

from marimba.utils.log import get_collection_logger, setup_logging

logger = get_collection_logger()

app = typer.Typer(
    help="Create a new MarImBA collection, instrument or deployment.",
    no_args_is_help=True,
)


def get_base_templates_path() -> str:
    base_templates_path = Path(os.path.abspath(__file__)).parent.parent.parent / "templates"
    logger.info(f'Setting MarImBA base templates path to: "{base_templates_path}"')
    return str(base_templates_path)


def check_template_exists(base_templates_path, template_name, template_type) -> str:
    logger.info(f"Checking that the provided MarImBA [bold]{template_type}[/bold] template exists...")
    template_path = Path(base_templates_path) / template_name / template_type

    if os.path.isdir(template_path):
        logger.info(f"MarImBA [bold]{template_type}[/bold] template [bold]{Path(template_name) / template_type}[/bold] exists!")
    else:

        print(
            Panel(
                f"The provided [bold]{template_type}[/bold] template name [bold]{Path(template_name) / template_type}[/bold] does not exists at {template_path}",
                title="Error",
                title_align="left",
                border_style="red",
            )
        )
        raise typer.Exit()

    return str(template_path)


def check_output_path_exists(output_path, command):
    logger.info(f"Checking that the provided MarImBA [bold]{command}[/bold] output path exists...")

    if os.path.isdir(output_path):
        logger.info(f'MarImBA [bold]{command}[/bold] output path "[bold]{output_path}[/bold]" exists!')
    else:
        print(
            Panel(
                f'The provided MarImBA [bold]{command}[/bold] output path "[bold]{output_path}[/bold]" does not exists.',
                title="Error",
                title_align="left",
                border_style="red",
            )
        )
        raise typer.Exit()


@app.command()
def collection(
        output_path: str = typer.Argument(..., help="Root path to create new MarImBA collection."),
        template_name: str = typer.Argument(..., help="Name of predefined MarImBA project template."),
):
    """
    Create a new MarImBA collection.
    """
    logger.info(f"Executing the MarImBA [bold]new collection[/bold] command.")

    # Get base template path and check that it exists
    base_templates_path = get_base_templates_path()
    template_path = check_template_exists(base_templates_path, template_name, "collection")

    # Check output path exists
    check_output_path_exists(output_path, "collection")

    # Run cookiecutter
    cookiecutter(
        template=template_path,
        output_dir=output_path,
        extra_context={"datestamp": datetime.today().strftime("%Y-%m-%d")}
    )


@app.command()
def instrument(
        collection_path: str = typer.Argument(..., help="Root path to MarImBA collection."),
        template_name: str = typer.Argument(..., help="Name of predefined MarImBA project template."),
):
    """
    Create a new MarImBA instrument in a collection.
    """
    setup_logging(collection_path)

    logger.info(f"Executing the MarImBA [bold]new instrument[/bold] command.")

    # Get base template path and check that it exists
    base_templates_path = get_base_templates_path()
    template_path = check_template_exists(base_templates_path, template_name, "instrument")

    # Check output path exists
    output_path = Path(collection_path) / "instruments"
    check_output_path_exists(output_path, "instrument")

    # Run cookiecutter
    try:
        cookiecutter(
            template=template_path,
            output_dir=output_path,
            extra_context={"datestamp": datetime.today().strftime("%Y-%m-%d")}
        )
    except OutputDirExistsException as e:
        exception_path = str(e).split("\"")[1]
        print(
            Panel(
                f'A MarImBA [bold]instrument[/bold] already exists at: "{exception_path}"',
                title="Error",
                title_align="left",
                border_style="red",
            )
        )
        raise typer.Exit()
    # TODO: Need to figure out how to catch this exception properly and feed back into rich exceptions
    except Exception as e:
        print(e)


@app.command()
def deployment(
        collection_path: str = typer.Argument(..., help="Path to root MarImBA collection."),
        template_name: str = typer.Argument(..., help="Name of predefined MarImBA project template."),
        instrument_id: str = typer.Argument(..., help="Instrument ID when adding a new deployment."),
):
    """
    Create a new MarImBA deployment for an instrument in a collection.
    """
    setup_logging(collection_path)

    logger.info(f"Executing the MarImBA [bold]new deployment[/bold] command.")

    # Get base template path and check that it exists
    base_templates_path = get_base_templates_path()
    template_path = check_template_exists(base_templates_path, template_name, "deployment")

    # Check output path exists
    output_path = Path(collection_path) / "instruments" / instrument_id / "work"
    check_output_path_exists(output_path, "deployment")

    # Run cookiecutter
    cookiecutter(
        template=str(template_path),
        output_dir=output_path,
        extra_context={"datestamp": datetime.today().strftime("%Y-%m-%d")}
    )
