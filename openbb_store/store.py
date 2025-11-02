"""Store Class."""

# pylint: disable=too-many-branches,too-many-return-statements,too-many-arguments,
# pylint: disable=too-many-lines,too-many-positional-arguments,too-many-locals,too-many-statements
# flake8: noqa: PLC0415,PLR0912,PLR0915,PLR0917

import hashlib
import json
import lzma
import os
import pickletools
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import dill as pickle
from openbb_core.app.model.obbject import OBBject
from openbb_core.provider.abstract.data import Data
from pydantic import Field, PrivateAttr

if TYPE_CHECKING:
    from pandas import DataFrame, ExcelFile


class Store(Data):
    """The Store class is a data model for storing,
    organizing, and retrieving OBBjects or other Python objects.

    The class provides methods to add, retrieve, and save groups of data objects
    to memory or file as a transportable, compressed, SHA1 signed pickle.

    It is a shared resource across the Python session,
    when initialized globally within the OpenBB Platform as an OBBject extension.

    **Note**: As an extension, the OpenBB user preference, 'output_type', must be set to 'OBBject'.

    Supported Data Types: OBBject, Data, ExcelFile, DataFrame, Dict, List, str

    Parameters
    ----------
    filename : Optional[str]
        Initialize the class with a previously exported file.
        Use the full path to the file without the '.xz' extension.
    names : Optional[str]
        A comma-separated list of names to load from the file.
        If None, all stored data objects are loaded.

    Properties
    ----------
    user_data_directory : str
        The read/write directory. The parent path is resolved by the OpenBB User Preference, 'data_directory'.
        This is overridden by entering the complete path to the file for IO operations.
    verbose : bool
        Set as False to silence IO operation confirmation messages.
    list_stores : List
        List of stored data object keys.
    directory : Dict
        Directory of stored data objects. Each entry contains a name, description, and a preview of the schema.
    defaults : List
        List of stores loaded by default. Only exists when Store is used as an OBBject extension.

    Methods
    -------
    add_store(
        name: str,
        data: Union[OBBject, Data, DataFrame, Dict, ExcelFile, List, str],
        description: Optional[str] = None
    ):
        Add a stored data object with a unique name, data, and optional description.

    get_store(
        name: str = "",
        element: Literal["OBBject", "dataframe", "dict", "llm", "chart"] = "dataframe",
        sheet_name: Optional[str] = None,
        pd_query: Optional[str] = None,
        dict_orient: str = "list",
        chart_params: Optional[Dict[str, Any]] = None
        **excel_kwargs
    ):
        Get a stored data object by name. When only one object is stored, the name parameter is optional.
        The element parameter specifies the return type, and is only valid for OBBjects.

        A DataFrame is returned when element is set to 'dataframe', and a Pandas query string can be applied.

    add_to_defaults(name: str):
        Add a stored data object to the defaults list. Only exists when Store is used as an OBBject extension.

    remove_from_defaults(name: str):
        Remove a stored data object from the defaults list. Only exists when Store is used as an OBBject extension.

    get_schema(name: str):
        Get the schema for a stored data object by name.

    update_store(
        name: str,
        data: Union[OBBject, Data, DataFrame, Dict, ExcelFile, List, str],
        description: Optional[str] = None
    ):
        Overwrite an existing stored data object with a new data object.

    append_store(
        name: str,
        data: Any,
        target_key: str | int | None
    ):
        Append a new object to an existing store.

    remove_store(name: str):
        Remove a stored data object by name.

    clear_stores():
        Clear all stored data objects from memory.

    save_store_to_file(filename: str, names: Optional[List[str]] = None):
        Save the Store object, or a list of store names, to a compressed shelf file.

    load_store_from_file(filename: str, names: Optional[str] = None):
        Load an exported Store from file.

    load_from_excel(file: Union[bytes, str], name: str, description: Optional[str] = None, **excel_file_kwargs):
        Load an Excel spreadsheet from a file or bytes object,
        adds it as a stored data object, and returns the ExcelFile object.

    load_defaults():
        Clear all stores and load the defaults. Only exists when Store is used as an OBBject extension.
    """

    user_data_directory: str = Field(
        description="The read/write directory."
        + " When initialized by OBBject, the parent path is resolved by the OpenBB User Preference, 'data_directory'."
        + " This is overridden by entering the complete path to the file for IO operations.",
        default="",
    )
    verbose: bool = Field(
        default=True,
        description="Set as False to silence IO operation confirmation messages.",
    )
    directory: dict[str, Any] = Field(
        default_factory=dict,
        description="Directory of stored data objects."
        + " Each entry contains a name, description, and a preview of the schema.",
    )
    archives: dict[str, Any] = Field(
        default_factory=dict,
        description="Compressed stored data objects.",
    )
    schemas: dict[str, Any] = Field(
        default_factory=dict,
        description="Compressed schema for each stored data object. This field is not meant to be accessed directly."
        + " Use 'directory' to describle all entries,"
        + " or the 'get_schema' method to retrieve the schema for a stored data object.",
    )

    _defaults: list = PrivateAttr(default_factory=list)

    def __init__(
        self, filename: str | None = None, names: list[str] | str | None = None, **data
    ):
        """Initialize the Store object."""
        super().__init__(**data)
        if filename:
            self.load_store_from_file(filename, names)

    @property
    def list_stores(self) -> list:
        """List all keys to stored data objects."""
        return list(self.directory)

    def add_store(
        self,
        name: str,
        data: "OBBject | Data | DataFrame | ExcelFile | dict | list | str",
        description: str | None = None,
    ) -> str | None:
        """Add a stored data object."""
        # pylint: disable=import-outside-toplevel
        if name in self.directory:
            raise KeyError(
                f"Data store '{name}' already exists."
                + " Use 'update_store' to overwrite the existing data."
            )

        data_class = data.__class__.__name__ or ""
        schema = None
        schema_repr = ""

        if "OBBject" in data_class:
            fields_set = data.to_df(index=None).columns.to_list()  # type: ignore
            length = len(data.results) if isinstance(data.results, list) else 1  # type: ignore
            if fields_set[0] == 0:
                fields_set = data.to_df(index=None).iloc[:, 0].to_list()  # type: ignore
            schema = {
                "length": length,
                "fields_set": fields_set,
                "data_model": (
                    data.results.model_copy()  # type: ignore
                    if length == 1
                    else data.results[0].model_copy()  # type: ignore
                ),
                "created_at": (
                    str(data.extra["metadata"].timestamp)  # type: ignore
                    if hasattr(data.extra, "metadata")  # type: ignore
                    else datetime.now()
                ),
                "uid": data.id,  # type: ignore
            }
            schema_repr = str(schema)[:80]
        elif data_class == "Data" or (
            data_class == "list"
            and len(data) == 1  # type: ignore
            and data[0].__class__.__name__ == "Data"  # type: ignore
        ):
            schema = data.model_copy()  # type: ignore
            schema_repr = schema.__repr__()[:80]  # pylint: disable=C2801
        elif data_class == "dict" and data.get("type") == "ExcelFile":  # type: ignore
            schema = {
                "sheet_names": data.get("sheet_names", []),  # type: ignore
            }
            schema_repr = "sheet_names: " + str(schema.get("sheet_names", ""))[:67]
        elif data_class == "dict":
            types_map = self._map_dict_types(data)
            schema = {
                "length": len(data),  # type: ignore
                "keys": list(data.keys()),  # type: ignore
                "types": list(set(v for v in self._extract_dict_types(types_map))),
                "types_map": types_map,  # type: ignore
            }
            schema_repr = str(schema)[:80]
        elif data_class == "list":
            schema = {
                "length": len(data),  # type: ignore
                "types": list(set([d.__class__.__name__ for d in data])),  # type: ignore  # pylint: disable=R1718
                "first_value": data[0],  # type: ignore
                "last_value": data[-1],  # type: ignore
            }
            schema_repr = str(schema)[:80]
        elif data_class == "DataFrame":
            schema = {
                "length": len(data.index),  # type: ignore
                "width": len(data.columns),  # type: ignore
                "columns": data.columns,  # type: ignore
                "index": data.index,  # type: ignore
                "types_map": data.dtypes,  # type: ignore
            }
            schema_repr = str(schema)[:80]
        elif data_class == "str":
            schema = {
                "length": len(data),  # type: ignore
                "first_80_chars": data[:80],  # type: ignore
            }
            schema_repr = str(schema)
        else:
            raise ValueError(f"Data type, {data_class}, not supported.")
        max_len = 80
        schema_repr = (
            schema_repr + "..." if len(schema_repr) >= max_len else schema_repr
        )
        compressed_schema = self._compress_store(schema)
        self.schemas.update({name: compressed_schema})
        directory_entry = {
            name: {
                "description": description,
                "data_class": data_class,
                "schema_preview": schema_repr,
            },
        }
        compressed_store = self._compress_store(data)
        self.archives.update({name: compressed_store})
        self.directory.update(directory_entry)
        if self.verbose:
            return f"Data store '{name}' added successfully."
        return None

    def get_store(  # noqa: PLR0911  # pylint: disable=R0917
        self,
        name: str = "",
        element: Literal["OBBject", "dataframe", "dict", "llm", "chart"] = "dataframe",
        sheet_name: str | None = None,
        pd_query: str | None = None,
        dict_orient: str = "list",
        chart_params: dict[str, Any] | None = None,
        **excel_kwargs,
    ) -> Any:
        """Get a stored data object.

        Parameters
        ----------
        name: str
            The name of the stored object.
        element: Literal["OBBject", "dataframe", "dict", "llm", "chart"]
            The element to retrieve. Ignored if the stored object is not an instance of "OBBject".
        sheet_name: Optional[str]
            The name of the Excel worksheet to return from the ExcelFile object.
            Ignored if the stored object is not an instance of "ExcelFile".
        pd_query: Optional[str]
            A Pandas query string to pass before output.
            Valid only when the expected output is passed through a DataFrame.
        dict_orient: Optional[str]
            The orientation of the dictionary.
        chart_params: Optional[Dict[str, Any]]
            Dictionary of `chart_params` to pass to `to_chart`.
            Ignored if the stored object is not an instance of "OBBject".
        excel_kwargs: Optional[Dict[str, Any]]
            Additional keyword arguments for the `read_excel` method.

        Returns
        -------
        Any
            The stored data object or requested element.
        """
        # pylint: disable=import-outside-toplevel
        from pandas import DataFrame

        if not name:
            name = self.list_stores[0] if self.list_stores else ""  # type: ignore
        if name not in self.directory:
            raise KeyError(f"Data store '{name}' does not exist.")
        decompressed_data = self._decompress_store(self.archives[name])
        data_class = self.directory[name]["data_class"]
        if data_class == "OBBject":
            obbject = OBBject.model_validate(decompressed_data)
            if hasattr(obbject, "charting") and hasattr(obbject.chart, "fig"):
                # pylint: disable=import-outside-toplevel
                from openbb_charting.core.openbb_figure import OpenBBFigure  # noqa

                obbject.chart.fig = OpenBBFigure(obbject.chart.fig)  # type: ignore
                # obbject.chart.fig.layout = obbject.chart.content["layout"]
                obbject.chart.fig.update(  # type: ignore
                    dict(
                        layout={
                            k: v if v is not None else None
                            for k, v in obbject.chart.content["layout"].items()  # type: ignore
                        },
                        data=obbject.chart.content["data"],  # type: ignore
                    ),
                    overwrite=False,
                )

            if (
                element not in ["OBBject", "dataframe", "dict", "llm", "chart"]
                and element not in obbject.accessors
            ):
                raise ValueError(
                    f"Invalid element '{element}'. Choose from 'OBBject', 'dataframe', 'dict', 'llm', or 'chart'."
                )
            if element == "OBBject":
                return obbject

            if element == "llm":
                return obbject.to_llm()

            if element in obbject.accessors and element != "charting":
                return getattr(obbject, element)

            if element == "chart":
                msg = "Charting extension is not installed. Install with `pip install openbb-charting`."
                try:
                    # pylint: disable=unused-import,import-outside-toplevel
                    from openbb_charting.core.openbb_figure import OpenBBFigure  # noqa

                except ImportError as e:
                    raise ImportError(msg) from e

                if not hasattr(obbject, "charting"):
                    raise ImportError(msg)

                if hasattr(obbject.chart, "fig") and chart_params is None:
                    return obbject.charting.fig.show(external=True)  # type: ignore

                chart_params = chart_params if chart_params is not None else {}
                chart_params["render"] = False
                _ = obbject.charting.to_chart(data=obbject.results, **chart_params)  # type: ignore
                return obbject.show(external=True)  # type: ignore

            df = obbject.to_df(index=None)
            if pd_query:
                df = df.query(pd_query)
            if element == "dataframe":
                return df.convert_dtypes()
            if element == "dict":
                return df.to_dict(orient=dict_orient)  # type: ignore

        if data_class == "DataFrame":
            df = DataFrame(decompressed_data)
            schema = self.get_schema(name)
            df.columns = schema["columns"]
            df.index = schema["index"]
            df = df.astype(schema["types_map"], errors="ignore")
            return (
                df.query(pd_query).convert_dtypes() if pd_query else df.convert_dtypes()
            )
        if data_class == "dict" and decompressed_data.get("type") == "ExcelFile":
            # pylint: disable=import-outside-toplevel
            from pandas import ExcelFile, read_excel

            file_bytes = BytesIO(decompressed_data["bytes"])
            excel_kwargs = decompressed_data.get("excel_kwargs", {})
            excel_file = ExcelFile(file_bytes, **excel_kwargs)

            if sheet_name is not None:
                if sheet_name not in excel_file.sheet_names:
                    raise KeyError(
                        f"Sheet '{sheet_name}' not found in ExcelFile. Choices are: {excel_file.sheet_names}"
                    )
                excel_kwargs = excel_kwargs if excel_kwargs is not None else {}
                df = read_excel(excel_file, sheet_name, **excel_kwargs)
                if pd_query:
                    df = df.query(pd_query).convert_dtypes()
                return df
            return excel_file

        return decompressed_data

    def get_schema(self, name: str):
        """Get the schema for a stored data object."""
        if name not in self.directory:
            raise KeyError(f"Data store '{name}' does not exist.")
        compressed_schema = self.schemas[name]
        decompressed_schema = self._decompress_store(compressed_schema)

        if "data_model" in decompressed_schema:
            decompressed_schema["data_model"] = decompressed_schema[
                "data_model"
            ].schema(by_alias=False)

        return decompressed_schema

    def save_store_to_file(
        self, filename, names: list[str] | None = None
    ) -> str | None:
        """Save the Store object, or a list of store names, to a compressed shelf file."""
        names = names if names is not None else self.list_stores
        if isinstance(names, str):
            names = names.split(",")
        temp = {
            "archives": {name: self.archives[name] for name in names},
            "schemas": {name: self.schemas[name] for name in names},
            "directory": {name: self.directory[name] for name in names},
        }
        # Pickle the data and generate a signature
        pickled_data = pickletools.optimize(
            pickle.dumps(temp, protocol=pickle.HIGHEST_PROTOCOL)
        )
        signature = hashlib.sha1(pickled_data).hexdigest()  # noqa
        # Store the data and the signature.
        filename = (
            filename + ".xz"
            if filename.startswith("/")
            else self.user_data_directory + filename + ".xz"
        )
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        try:
            with lzma.open(filename, "wb") as f:
                f.write(pickle.dumps({"signature": signature, "data": pickled_data}))
        except Exception as e:
            raise e from e

        if self.verbose:
            return f"{filename} saved successfully."
        return None

    def load_store_from_file(
        self, filename, names: list[str] | str | None = None
    ) -> str | None:
        """Load the Store object from a file."""
        is_default = filename == "defaults"
        filename = (
            filename + ".xz"
            if filename.startswith("/")
            else self.user_data_directory + filename + ".xz"
        )

        if not os.path.exists(filename) and is_default is False:
            raise FileNotFoundError(f"File not found: {filename}")

        if not os.path.exists(filename) and is_default is True:
            return None

        pickled_data = None
        signature = None

        with lzma.open(filename, "rb") as f:
            file = pickle.load(f)  # noqa
            if (
                not isinstance(file, dict)
                or "signature" not in file
                or "data" not in file
            ):
                raise ValueError("Data integrity check failed")
            pickled_data = file["data"]
            signature = file["signature"]

        # Verify the signature
        if hashlib.sha1(pickled_data).hexdigest() != signature:  # noqa
            raise ValueError("Data integrity check failed")

        # Load the data
        temp = pickle.loads(pickled_data)  # noqa

        if names:
            names = names.split(",") if isinstance(names, str) else names
            for name in temp["directory"].copy():
                if name not in names:  # type: ignore
                    temp["directory"].pop(name)
                    temp["archives"].pop(name)
                    temp["schemas"].pop(name)

        self.archives.update(temp["archives"])
        self.schemas.update(temp["schemas"])
        self.directory.update(temp["directory"])

        if self.verbose:
            return f"{filename} loaded successfully."
        return None

    def load_from_excel(
        self,
        file: bytes | str,
        name: str,
        description: str | None = None,
        **excel_file_kwargs,
    ) -> "ExcelFile":
        """Load an Excel spreadsheet from a file, adds it as a stored data object, and returns the ExcelFile object.

        Parameters
        ----------
        file : Union[bytes, str]
            The file path, url, or bytes object. If the file is a path-like, it must include the file extension.
        name : str
            The name to assign to the stored object.
        description : Optional[str]
            A description of the stored object.
        **excel_file_kwargs
            Additional keyword arguments for the ExcelFile constructor.

        Returns
        -------
        ExcelFile
            The ExcelFile object.
        """
        try:
            excel_file, file_bytes = self._load_from_excel(file, **excel_file_kwargs)
        except Exception as e:
            raise e from e
        try:
            excel_data = {
                "type": "ExcelFile",
                "bytes": file_bytes.getvalue(),
                "sheet_names": excel_file.sheet_names,
                "excel_kwargs": excel_file_kwargs,
            }
            self.add_store(name=name, data=excel_data, description=description)
        except Exception as e:
            raise e from e

        if self.verbose:
            print(f"\nData store '{name}' added successfully.\n")  # noqa: T201

        return excel_file

    def update_store(
        self,
        name: str,
        data: "OBBject | Data | DataFrame | ExcelFile | dict | list | str",
        description: str | None = None,
    ) -> str | None:
        """Overwrite an existing stored data object."""
        if name not in self.directory:
            raise KeyError(f"Data store '{name}' does not exist.")

        self.remove_store(name)
        self.add_store(
            name=name,
            data=data,
            description=description,
        )
        if self.verbose:
            return f"Data store '{name}' updated successfully."
        return None

    def append_store(
        self,
        name: str,
        data: Any,
        target_key: str | int | None = None,
    ) -> str | None:
        """Append an object to an existing store.

        Parameters
        ----------
        name : str
            Name of the store to append.
        data : Any
            Incoming data to append store with.
        target_key : str | int | None
            Target dictionary key, list index number, or ExcelFile sheet name.
        """
        if name not in self.directory:
            raise KeyError(f"Data store '{name}' does not exist.")

        target_store = self.get_store(name)
        target_info = self.directory.get(name, {})

        if isinstance(target_store, OBBject):
            raise TypeError("OBBject-type stores do not support append.")

        def _is_index_key(value: Any) -> bool:
            if isinstance(value, int):
                return True
            if isinstance(value, str):
                try:
                    int(value)
                except ValueError:
                    return False
                return True
            return False

        if isinstance(target_store, list):
            incoming_items = data if isinstance(data, list) else [data]

            list_is_dicts = (
                all(isinstance(item, dict) for item in target_store)
                if target_store
                else all(isinstance(item, dict) for item in incoming_items)
            )
            existing_types = (
                {type(item) for item in target_store if item is not None}
                if target_store
                else set()
            )

            if existing_types and not list_is_dicts:
                for item in incoming_items:
                    if not any(isinstance(item, typ) for typ in existing_types):
                        expected = ", ".join(sorted(t.__name__ for t in existing_types))
                        raise TypeError(
                            f"Appending to list stores requires values of type: {expected}."
                        )

            if list_is_dicts:
                scalar_candidates = [
                    item for item in incoming_items if not isinstance(item, dict)
                ]
                if scalar_candidates and not (
                    isinstance(target_key, str) and not _is_index_key(target_key)
                ):
                    raise TypeError(
                        "Scalar updates to a list of dictionaries require a string target_key."
                    )

            index_key = None
            if target_key is not None and _is_index_key(target_key):
                index_key = int(target_key)
                if not (-len(target_store) <= index_key < len(target_store)):
                    raise IndexError(
                        f"Index '{index_key}' is out of range for list of size {len(target_store)}."
                    )
                if len(incoming_items) != 1:
                    raise TypeError(
                        "Updating a list index requires exactly one incoming value."
                    )
                replacement = incoming_items[0]
                if list_is_dicts and not isinstance(replacement, dict):
                    raise TypeError(
                        "List contains dictionaries. Provide a dictionary for index updates."
                    )
                if (
                    existing_types
                    and not list_is_dicts
                    and not any(isinstance(replacement, typ) for typ in existing_types)
                ):
                    expected = ", ".join(sorted(t.__name__ for t in existing_types))
                    raise TypeError(
                        f"Appending to list stores requires values of type: {expected}."
                    )
                target_store[index_key] = replacement
            elif list_is_dicts:
                scalar_items = [
                    item for item in incoming_items if not isinstance(item, dict)
                ]
                dict_items = [item for item in incoming_items if isinstance(item, dict)]

                if scalar_items:
                    if not target_store:
                        raise ValueError(
                            "Cannot broadcast scalar updates to an empty list of dictionaries."
                        )
                    if not all(target_key in entry for entry in target_store):
                        raise KeyError(
                            f"Key '{target_key}' not found in all dictionaries."
                        )
                    new_value = scalar_items[-1]
                    for entry in target_store:
                        entry[target_key] = new_value

                for item in dict_items:
                    matched = False
                    if (
                        isinstance(target_key, str)
                        and not _is_index_key(target_key)
                        and target_key in item
                    ):
                        for existing in target_store:
                            if (
                                target_key in existing
                                and existing[target_key] == item[target_key]
                            ):
                                existing.update(item)
                                matched = True
                    if not matched:
                        for existing in target_store:
                            if existing == item:
                                existing.update(item)
                                matched = True
                                break
                    if not matched:
                        target_store.append(item)
            else:
                for item in incoming_items:
                    if item in target_store:
                        index = target_store.index(item)
                        target_store[index] = item
                    else:
                        target_store.append(item)

        elif isinstance(target_store, dict):
            if target_key:
                target_key = (
                    str(target_key) if isinstance(target_key, int) else target_key
                )
                value = (
                    data[target_key]
                    if isinstance(data, dict) and target_key in data
                    else data
                )
                if not self._update_nested_dict(target_store, target_key, value):
                    raise KeyError(f"No {target_key} found in {target_store}")
            elif isinstance(data, dict):
                self._merge_nested_dict(target_store, data)
            else:
                raise TypeError("Appending to dict stores requires dict data.")

        elif target_store.__class__.__name__ == "DataFrame":
            try:
                # pylint: disable=import-outside-toplevel
                from pandas import DataFrame, concat
            except ImportError as exc:
                raise ImportError(
                    "Pandas is required to append DataFrame stores."
                ) from exc

            if not isinstance(data, DataFrame):
                raise TypeError(
                    "Appending to DataFrame stores requires DataFrame data."
                )

            target_df = target_store.copy()
            incoming_df = data.copy()

            if set(target_df.columns) != set(incoming_df.columns):
                mismatch = sorted(
                    set(target_df.columns).symmetric_difference(
                        set(incoming_df.columns)
                    )
                )
                raise KeyError(
                    "Incoming DataFrame columns must match existing columns."
                    + (f" Mismatch: {mismatch}" if mismatch else "")
                )

            incoming_df = incoming_df[target_df.columns]

            overlap_index = incoming_df.index.intersection(target_df.index)
            if not overlap_index.empty:
                target_df.loc[overlap_index] = incoming_df.loc[overlap_index]

            new_rows = incoming_df.loc[~incoming_df.index.isin(target_df.index)]
            if not new_rows.empty:
                target_df = concat([target_df, new_rows])

            target_store = target_df

        elif target_store.__class__.__name__ == "ExcelFile":
            try:
                # pylint: disable=import-outside-toplevel
                from pandas import DataFrame, ExcelWriter, concat
            except ImportError as exc:
                raise ImportError(
                    "Pandas is required to append ExcelFile stores."
                ) from exc

            if not isinstance(data, DataFrame):
                raise TypeError(
                    "Appending to ExcelFile stores requires DataFrame data."
                )

            stored_archive = self.archives.get(name)
            excel_kwargs: dict[str, Any] = {}
            if stored_archive is not None:
                existing_payload = self._decompress_store(stored_archive)
                if isinstance(existing_payload, dict):
                    excel_kwargs = existing_payload.get("excel_kwargs", {}) or {}

            sheets = {
                sheet: target_store.parse(sheet) for sheet in target_store.sheet_names
            }

            target_sheet = target_key
            if not target_sheet:
                base_name = "Sheet"
                suffix = 1
                existing_sheet_names = set(sheets)
                while f"{base_name}{suffix}" in existing_sheet_names:
                    suffix += 1
                target_sheet = f"{base_name}{suffix}"

            incoming_df = data.copy()

            if target_sheet in sheets:
                existing_df = sheets[target_sheet].copy()
                if set(existing_df.columns) != set(incoming_df.columns):
                    mismatch = sorted(
                        set(existing_df.columns).symmetric_difference(
                            set(incoming_df.columns)
                        )
                    )
                    raise KeyError(
                        "Incoming DataFrame columns must match existing columns."
                        + (f" Mismatch: {mismatch}" if mismatch else "")
                    )
                incoming_df = incoming_df[existing_df.columns]

                overlap_index = incoming_df.index.intersection(existing_df.index)
                if not overlap_index.empty:
                    existing_df.loc[overlap_index] = incoming_df.loc[overlap_index]

                new_rows = incoming_df.loc[~incoming_df.index.isin(existing_df.index)]
                if not new_rows.empty:
                    existing_df = concat([existing_df, new_rows])

                sheets[target_sheet] = existing_df
            else:
                sheets[target_sheet] = incoming_df

            buffer = BytesIO()
            with ExcelWriter(buffer, engine="openpyxl") as writer:
                for sheet_name_out, sheet_df in sheets.items():
                    sheet_df.to_excel(
                        writer,
                        sheet_name=sheet_name_out,
                        index=False,
                    )

            target_store = {
                "type": "ExcelFile",
                "bytes": buffer.getvalue(),
                "sheet_names": list(sheets),
                "excel_kwargs": excel_kwargs,
            }

        elif isinstance(target_store, str):
            if not isinstance(data, str):
                raise TypeError("Appending to string stores requires string data.")
            try:
                json.loads(target_store)
            except (TypeError, json.JSONDecodeError):
                pass
            else:
                raise TypeError("Appending to JSON string stores is not supported.")
            separator = ""
            if target_store:
                separator = "" if target_store.endswith("\n") else "\n"
            target_store = f"{target_store}{separator}{data}"

        else:
            raise TypeError(
                f"Target store object type is not supported.\n\n{target_info}\n"
            )

        data = target_store
        self.remove_store(name)
        self.add_store(
            name=name,
            data=data,
            description=target_info.get("description"),
        )
        if self.verbose:
            return f"{name} appended successfully."
        return None

    def remove_store(self, name: str) -> str | None:
        """Remove a stored data object by name."""
        if name not in self.directory:
            raise KeyError(f"Data store '{name}' does not exist.")
        _ = self.directory.pop(name, None)
        _ = self.archives.pop(name, None)
        _ = self.schemas.pop(name, None)
        if self.verbose:
            return f"Data store '{name}' removed successfully."
        return None

    def clear_stores(self) -> str | None:
        """Clear all stored data objects from memory."""
        self.directory = {}
        self.archives = {}
        self.schemas = {}
        if self.verbose:
            return "All data stores cleared."
        return None

    def _map_dict_types(self, data):
        """Map dictionary types."""

        def get_types_map(data):
            """Recursively map dictionary types."""
            types_map: dict = {}
            for k, v in data.items():
                if isinstance(v, dict):
                    types_map[k] = get_types_map(v)
                else:
                    types_map[k] = v.__class__.__name__
            return types_map

        return get_types_map(data)

    def _extract_dict_types(self, types_map):
        types = set()
        for value in types_map.values():
            if isinstance(value, dict):
                types.update(self._extract_dict_types(value))
            else:
                types.add(value)
        return types

    def _merge_nested_dict(self, target: dict, source: dict) -> None:
        """Deep-merge source into target."""
        for key, value in source.items():
            if (
                key in target
                and isinstance(target[key], dict)
                and isinstance(value, dict)
            ):
                self._merge_nested_dict(target[key], value)
            else:
                target[key] = value

    def _update_nested_dict(self, target: dict, key: str, value: Any) -> bool:
        """Recursively update the first matching key inside target."""
        if key in target:
            if isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_nested_dict(target[key], value)
            else:
                target[key] = value
            return True
        return any(
            isinstance(child, dict) and self._update_nested_dict(child, key, value)
            for child in target.values()
        )

    @staticmethod
    def _load_from_excel(
        file: bytes | str,
        **excel_file_kwargs,
    ) -> tuple["ExcelFile", BytesIO]:
        """Load an Excel spreadsheet.

        Parameters
        ----------
        file : Union[bytes, str]
            The file path or bytes object.
        **excel_file_kwargs
            Additional keyword arguments for the ExcelFile constructor.

        Returns
        -------
        ExcelFile
            The ExcelFile object.
        """
        try:
            # pylint: disable=import-outside-toplevel, unused-import
            import openpyxl  # noqa
            import xlrd  # noqa
            from pandas import ExcelFile
            from openbb_store.utils import get_random_agent

        except ImportError as e:
            raise ImportError(
                "The 'excel' extras are required for Excel IO. Install with `pip install openbb-store['excel']`."
            ) from e

        _ = excel_file_kwargs.pop("io", None)

        if isinstance(file, str) and file.startswith("http"):
            # pylint: disable=import-outside-toplevel
            from openbb_core.provider.utils.helpers import make_request

            attempts = 0

            def try_again(url):
                """Attempt to download the file again."""
                headers = {"User-Agent": get_random_agent()}
                return make_request(url, headers=headers)

            try:
                headers = excel_file_kwargs.pop(
                    "headers", {"User-Agent": get_random_agent()}
                )
                response = make_request(file, headers=headers)
                good_status = 200
                retry_status = 403
                max_attempts = 5
                if response.status_code == retry_status:
                    while attempts < max_attempts:
                        response = try_again(file)
                        attempts += 1
                        if response.status_code == good_status:
                            break
                        if attempts == max_attempts - 1:
                            raise RuntimeError(
                                f"Status Code: {response.status_code}"
                                + f"\nReason: {response.reason}"
                                + f"\nFailed to download file: {file}"
                            )
                if response.status_code not in (200, 403):
                    raise RuntimeError(
                        f"Status Code: {response.status_code}\nReason: {response.reason}\nFailed to download file: {file}"
                    )
                loaded_file = BytesIO(response.content)
            except Exception as e:
                raise e from e
        elif isinstance(file, bytes):
            loaded_file = BytesIO(file)
        elif isinstance(file, str):
            # Handle string path
            try:
                path = Path(file).expanduser().resolve()
                with open(path, "rb") as f:
                    loaded_file = BytesIO(f.read())
            except FileNotFoundError as e:
                raise FileNotFoundError(f"File not found: {file}") from e
            except Exception as e:
                raise e from e
        elif hasattr(file, "read") and hasattr(file, "seek"):
            # Handle file-like objects
            try:
                content = file.read()  # type: ignore
                file.seek(0)  # type: ignore
                loaded_file = BytesIO(content)
            except Exception as e:
                raise e from e
        else:
            raise TypeError(f"Unsupported file type: {type(file)}")

        if loaded_file is None:
            raise ValueError(f"Could not load file: {file}")

        try:
            file_bytes = BytesIO(loaded_file.getvalue())
            loaded_file.seek(0)
            excel_file = ExcelFile(loaded_file, **excel_file_kwargs)
        except Exception as e:
            raise e from e

        return excel_file, file_bytes

    @classmethod
    def _compress_store(cls, data):
        """Compress a stored data object."""
        # pylint: disable=import-outside-toplevel
        from copy import copy

        has_chart = False
        if data.__class__.__name__ == "OBBject":
            # Create a new instance from a copy of the original OBBject.
            new_data = data.model_copy()
            chart = copy(data.chart)
            # This is to prevent a key error when restoring the Chart attribute.
            if chart and hasattr(chart, "fig"):
                from plotly.graph_objects import Figure

                fig = Figure(chart.fig)
                fig.update(
                    dict(data=chart.content["data"], layout=chart.content["layout"])
                )
                setattr(new_data.chart, "fig", fig)
                has_chart = True

            accessors = list(new_data.accessors) if hasattr(data, "accessors") else []
            # This is to prevent "cannot pickle '_contextvars.Context' object" error
            # If the extension is installed, it will be activated again on restore.
            for ext in accessors:
                if hasattr(new_data, ext):
                    del new_data.__dict__[ext]
        else:
            new_data = copy(data)

        pickled_data = pickletools.optimize(pickle.dumps(new_data))
        signature = hashlib.sha1(pickled_data).hexdigest()  # noqa
        if has_chart is True:
            setattr(new_data, "chart", chart)
            setattr(data, "chart", chart)

        return {"archive": lzma.compress(pickled_data), "signature": signature}

    @staticmethod
    def _decompress_store(data):
        """Decompress a stored data object."""
        decompressed_data = lzma.decompress(data["archive"])
        signature = data["signature"]
        if hashlib.sha1(decompressed_data).hexdigest() != signature:  # noqa
            raise ValueError("Data signature does not match!")
        return pickle.loads(decompressed_data)  # noqa

    def __repr__(self):
        """Return a string representation of the object."""
        names = self.list_stores  # type: ignore
        if names == [""]:
            return f"{self.__class__.__name__}\n\nNo archives added."
        stores: list = []
        for name in names:
            string = (
                f"\n\n    {name}:\n        Data Class: {self.directory[name]['data_class']}"
                + f"\n        Description: {self.directory[name].get('description')}"
                + f"\n        Schema Preview: {self.directory[name].get('schema_preview')}"
            )
            stores.append(string)
        return f"\n{self.__class__.__name__} Archive {''.join(stores) if stores else 'No stores added.'}"
