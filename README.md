# OBBject Store Extension

`openbb-store` is an [OBBject](https://docs.openbb.co/platform/developer_guide/obbject) extension for storing and retrieving OBBjects, Data, DataFrames, ExcelFiles, dictionaries, lists, and strings.

Each entry is stored as a compressed pickle, with SHA1 signature, using the LZMA module with the "xz" algorithm set to maximum compression.

The purpose of this module is to efficiently persist binary objects in-memory, and/or to-disk, in a format that is transportable over a network.
An example use-case is a server-side cache for redistributing common data resources among various API endpoints and callbacks. Another is to persist frequently-accessed items like, lists and maps of ticker symbols or, static assets in a format suitable for programmatic utility.

## Installation

### PyPI

Install from PyPI with:

```console
pip install openbb-store
```

### From Source

After cloning the repo, navigate into the project's folder, create a new Python environment, then install with:

```sh
pip install -e .
```

## Usage

Every output from the OpenBB Platform Python interface - when `obb.user.preferences.output_type = "OBBject"` - will have the `store` attribute.

### Importing

Importing is only necessary when used as a standalone class, and it needs to be initialized. The __init__ will accept a filename or path that can be used to load a previously exported object into memory.

```python
from openbb_store.store import Store

store = Store()
```

**Note:** Functionality specific to operating as an OpenBB Platform extension - such as defaults - are not available in this mode.

### Store Class

Within the OpenBB Platform, the extension acts as Global with methods to add, retrieve, and save groups of data objects to memory or file in a transportable and compressed format.

When used as standalone, the `user_data_directory` property (preference) should be set to the desired read/write directory
upon initialization. Alternatively, specify the complete path to the file when using the IO methods' `filename` parameter.

### Supported Data Types

The following is a list of supported data objects:

- OBBject
- Data (generic OpenBB Data class)
- DataFrame
- List
- Dictionary
- String
- ExcelFile (Pandas instance)

The contents of any object being added must be serializable.

### Add Data

```python
from openbb import obb  # If `openbb` is not installed, install it with `pip install openbb`

data = obb.equity.price.historical("NVDA", provider="yfinance", start_date="2023-01-01", end_date="2023-12-31")
data.store.add_store(data=data, name="nvda2023")
```

A confirmation will display unless the "verbose" property is set to `False`.

```console
"Data store 'nvda2023' added successfully."
```

Additional data can be added to the collection, and then exported as a single package.

```python
data = obb.equity.fundamental.metrics("NVDA", provider="yfinance")
data.store.add_store(data = data.to_df().set_index("symbol").T, name="nvdaMetrics", description="Key Valuation Metrics for NVDA.")
```

```console
"Data store 'nvdaMetrics' added successfully."
```

### Directory Of Objects

An inventory of stored objects is displayed with the 'directory' property.

```python
data.store.directory
```

```console
{'nvda2023': {'description': None,
  'data_class': 'OBBject',
  'schema_preview': "{'length': 250, 'fields_set': ['open', 'high', 'low', 'close', 'volume', 'split_..."},
 'nvdaMetrics': {'description': 'Key Valuation Metrics for NVDA.',
  'data_class': 'DataFrame',
  'schema_preview': "{'length': 34, 'width': 1, 'columns': Index(['NVDA'], dtype='object', name='symb..."}}
```

### Schemas

Metadata related to the schema are stored independent of the actual data store.
Schemas are retrieved with the `get_schema` method, using the assigned 'name' as the key.

Example DataFrame schema:

```python
data.store.get_schema("nvdaMetrics")
```

```console
{'length': 34,
 'width': 1,
 'columns': Index(['NVDA'], dtype='object', name='symbol'),
 'index': Index(['market_cap', 'pe_ratio', 'forward_pe', 'peg_ratio', 'peg_ratio_ttm',
        'enterprise_to_ebitda', 'earnings_growth', 'earnings_growth_quarterly',
        'revenue_per_share', 'revenue_growth', 'enterprise_to_revenue',
        'quick_ratio', 'current_ratio', 'debt_to_equity', 'gross_margin',
        'operating_margin', 'ebitda_margin', 'profit_margin',
        'return_on_assets', 'return_on_equity', 'dividend_yield',
        'dividend_yield_5y_avg', 'payout_ratio', 'book_value', 'price_to_book',
        'enterprise_value', 'overall_risk', 'audit_risk', 'board_risk',
        'compensation_risk', 'shareholder_rights_risk', 'beta',
        'price_return_1y', 'currency'],
       dtype='object'),
 'types_map': symbol
 NVDA    object
 dtype: object}
```

Example Pydantic model schema:

```python
data.store.get_schema("nvda2023")
```

```console
{'length': 250,
 'fields_set': ['open',
  'high',
  'low',
  'close',
  'volume',
  'split_ratio',
  'dividend'],
 'data_model': {'additionalProperties': True,
  'description': 'Yahoo Finance Equity Historical Price Data.',
  'properties': {'date': {'anyOf': [{'format': 'date', 'type': 'string'},
     {'format': 'date-time', 'type': 'string'}],
    'description': 'The date of the data.',
    'title': 'Date'},
   'open': {'description': 'The open price.',
    'title': 'Open',
    'type': 'number'},
   'high': {'description': 'The high price.',
    'title': 'High',
    'type': 'number'},
   'low': {'description': 'The low price.', 'title': 'Low', 'type': 'number'},
   'close': {'description': 'The close price.',
    'title': 'Close',
    'type': 'number'},
   'volume': {'anyOf': [{'type': 'number'},
     {'type': 'integer'},
     {'type': 'null'}],
    'default': None,
    'description': 'The trading volume.',
    'title': 'Volume'},
   'vwap': {'anyOf': [{'type': 'number'}, {'type': 'null'}],
    'default': None,
    'description': 'Volume Weighted Average Price over the period.',
    'title': 'Vwap'},
   'split_ratio': {'anyOf': [{'type': 'number'}, {'type': 'null'}],
    'default': None,
    'description': 'Ratio of the equity split, if a split occurred.',
    'title': 'Split Ratio'},
   'dividend': {'anyOf': [{'type': 'number'}, {'type': 'null'}],
    'default': None,
    'description': 'Dividend amount (split-adjusted), if a dividend was paid.',
    'title': 'Dividend'}},
  'required': ['date', 'open', 'high', 'low', 'close'],
  'title': 'YFinanceEquityHistoricalData',
  'type': 'object'},
 'created_at': '2024-06-18 13:08:44.778360',
 'uid': '06671e94-d271-7d4f-8000-43094acbb703'}
```

### Restore Data

Restore data from the Store extension by using the `get_store` method. Each archive and pickled object are validated against a signature before opening.

```python
data.store.get_store("nvdaMetrics")
```

|                           | NVDA            |
|:--------------------------|:----------------|
| market_cap                | 2933787983872.0 |
| pe_ratio                  | 56.15023        |
| forward_pe                | 29.825434       |
| peg_ratio                 | 0.76            |
| peg_ratio_ttm             | 1.2189          |
| enterprise_to_ebitda      | 45.047          |
| earnings_growth           | 1.68            |
| earnings_growth_quarterly | 1.682           |
| revenue_per_share         | 3.91            |
| revenue_growth            | 1.224           |
| enterprise_to_revenue     | 28.619          |
| quick_ratio               | 3.503           |
| current_ratio             | 4.269           |
| debt_to_equity            | 17.221          |
| gross_margin              | 0.75975996      |
| operating_margin          | 0.62057         |
| ebitda_margin             | 0.6353          |
| profit_margin             | 0.55041003      |
| return_on_assets          | 0.55258         |
| return_on_equity          | 1.23767         |
| dividend_yield            | 0.0004          |
| dividend_yield_5y_avg     | 0.001           |
| payout_ratio              | 0.010299999     |
| book_value                | 2.368           |
| price_to_book             | 50.506756       |
| enterprise_value          | 2756181229568   |
| overall_risk              | 8.0             |
| audit_risk                | 7.0             |
| board_risk                | 10.0            |
| compensation_risk         | 4.0             |
| shareholder_rights_risk   | 6.0             |
| beta                      | 1.673           |
| price_return_1y           | 1.7639759       |
| currency                  | USD             |

When the stored object is an instance of `OBBject`, the element to retrieve can be isolated with the `element` parameter.
By default, it is "dataframe". When set as "OBBject", the object is restored in its original form.

```python
data.store.get_store("nvda2023", element="OBBject")
```

```console
OBBject

id: 06671e94-d271-7d4f-8000-43094acbb703
results: [{'date': datetime.date(2023, 1, 3), 'open': 14.85099983215332, 'high': 14...
provider: yfinance
warnings: None
chart: None
extra: {'metadata': {'arguments': {'provider_choices': {'provider': 'yfinance'}, 's...
```

### Exporting/Importing

Any item(s) loaded into the extension can be exported to file as a ".xz" archive.
A list of "names" isolates specific objects for writing to disk. Without supplying names,
all entries are exported.

```python
data.store.save_store_to_file(filename="nvda")
```

Importing works the same way, and a list of "names" can also be included to load only the desired elements.

```python
data.store.load_store_from_file(filename="nvda")
```

The default path can be overridden by including the complete path, beginning with "/", in the filename.
Do not include the file extension with the name.

### Loading Excel Files

The ability to handle Excel files requires installing the "excel" extras.

```sh
pip install openbb-store["excel"]
```

Once installed, files can be loaded from a local path or a URL by calling the `load_from_excel` method.

The [`ExcelFile`](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.ExcelFile.html) object will be returned,
in addition to being loaded into memory.

```python
data.store.load_from_excel(
  file="https://www.spglobal.com/spdji/en/documents/additional-material/sp-500-eps-est.xlsx",
  name="sp500_eps",
  description="S&P 500 EPS estimates."
)
```

```sh
Data store 'sp500_eps' added successfully.

<pandas.io.excel._base.ExcelFile at 0x1262f62d0>
```

ExcelFile objects will have a schema consiting of a list of sheet names.

```python
data.store.get_schema("sp500_eps")
```
```sh
{'sheet_names': ['ESTIMATES&PEs',
  'SECTOR EPS',
  'QUARTERLY DATA',
  'SALES',
  'BEATS AND SHARES',
  'FORWARD SCHEDULE']}
```

#### Individual sheets can be recalled via the `get_store` method, adding the `sheet_name` parameter.

```python
data.store.get_store("sp500_eps", sheet_name="SALES", skiprows=4).iloc[:12, :4]
```

| QUARTERLY SALES PER SHARE   |   % CHG Q2/Q1 |   % CHG Q2/Q2 |   2024-06-28  |
|:----------------------------|--------------:|--------------:|--------------:|
| ENERGY                      |    0.0675681  |    0.0872589  |     134.198   |
| MATERIALS                   |    0.0699618  |   -0.0240995  |      65.3953  |
| INDUSTRIALS                 |    0.0479355  |    0.0151455  |     114.577   |
| CONSUMER DISCRETIONARY      |    0.0900365  |    0.0115968  |     162.86    |
| CONSUMER STAPLES            |    0.00634981 |    0.0179107  |     139.538   |
| HEALTH CARE                 |    0.0416614  |    0.0899313  |     254.513   |
| FINANCIALS                  |    0.0223595  |    0.0718522  |      79.645   |
| INFORMATION TECHNOLOGY      |    0.0259091  |    0.125514   |     120.964   |
| COMMUNICATION SERVICES      |    0.0309041  |    0.0937237  |      20.3298  |
| UTILITIES                   |   -0.0882947  |    0.033352   |      33.5973  |
| REAL ESTATE*                |    0.0143508  |    0.00782597 |       9.93927 |
| S&P 500                     |    0.0355043  |    0.0575002  |     488.705   |

### Setting Default Stores

When used as an OBBject extension, a default state can be configured as a starting point for every OpenBB Platform Python session.

Adding and removing defaults works the same way as adding and removing objects.

#### Add To Defaults

```python
data.store.add_to_defaults("sp500_eps")
```
```sh
'sp500_eps added to defaults.'
```

#### Remove From Defaults

```python
data.store.remove_from_defaults("sp500_eps")
```
```sh
'sp500_eps removed from defaults.'
```
