# Development

## Install pyenv and download Python 3.11.2

```bash
pyenv install 3.11.2
pyenv local 3.11.2
```

## To create a virtual environment:

```bash
python3 -m venv venv
```

## To use pre-commit hooks locally, install pre-commit:

```bash
pip install pre-commit
pre-commit install
```

## To format code
### Install dependencies:

```bash
pip install black isort flake8
```

### Run the following command (in the root directory of the project):

```bash
chmod +x format-all.sh
./format-all.sh
```

## To run tests using pytest

### Install dependencies:
```bash
pip install pytest
```

### Run the following command (in the root directory of the project):

```bash
pytest
```
