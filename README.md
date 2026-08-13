Bounce-Infinity

Custom ERPNext app for Bounce.

## GRN QC allocation

The app extends **Quality Inspection** with a row-level, partial QC allocation flow for submitted
Purchase Receipts. Select **QC Item**, click **Get GRN for QC**, and enter accepted/rejected quantities
against one or more pending Purchase Receipt rows. Only submitted Quality Inspections consume the
pending quantity; cancelled and draft inspections do not.

The server validates every allocation against its exact `Purchase Receipt Item`, recalculates pending
quantities from submitted inspections, and locks the source row while submitting to prevent concurrent
over-allocation.

Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app bounce
```

For an existing installation, update the app and synchronize the DocType and custom fields:

```bash
bench --site your-site migrate
bench build --app bounce
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/bounce
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade
### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
=======
# Bounce-Infinity
Custom ERPNext app for Bounce
>>>>>>> 14d51b795da33602cbc31f90a5d909fee7013716
