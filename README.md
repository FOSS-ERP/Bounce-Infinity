Bounce-Infinity

Custom ERPNext app for Bounce.

## Incoming QC workflow

The **Incoming QC Workbench** (`/app/incoming-qc-workbench`) lists submitted Purchase Receipt Item rows
that still have pending QC quantity. QC users can filter by Item, Purchase Receipt, Supplier, or receipt
date, select multiple rows for the same Item, and create an **Incoming Quality Inspection**.

The inspection records accepted and rejected quantities against the exact Purchase Receipt Item rows.
Rejection Reason is mandatory when any quantity is rejected. Submitted inspections automatically create
accepted and rejected Material Transfer Stock Entries, maintain row-level links back to the Purchase
Receipt and QC allocation, and update each Purchase Receipt to **QC Pending**, **Partial QC Done**, or
**QC Completed**.

Configure routing on each Quality Warehouse:

1. Mark destination warehouses as **Is QC Accepted Warehouse** or **Is QC Rejected Warehouse**.
2. On the Quality Warehouse, select its **QC Accepted Material Warehouse** and **QC Rejected Material Warehouse**.
3. Ensure QC users can create and submit Material Transfer Stock Entries.

Only classified destinations from the same company are selectable. Cancelling an Incoming Quality
Inspection cancels its generated Stock Entries and reopens the affected quantities. The app does not
modify the standard ERPNext Quality Inspection form.

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

- CI: Installs ERPNext and this app, then runs server tests for pull requests and pushes to `version-16`.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
