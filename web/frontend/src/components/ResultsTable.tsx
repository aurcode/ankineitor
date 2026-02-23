import { FormEvent, useState } from "react";

import { RunResultsResponse } from "../types/pipeline";

interface ResultsTableProps {
  runId: string | null;
  results: RunResultsResponse | null;
  isLoading: boolean;
  currentPage: number;
  totalPages: number;
  search: string;
  onSearchChange: (value: string) => void;
  onSearchSubmit: () => void;
  onPageChange: (page: number) => void;
  onAddCategory: (category: string) => void;
  onDownloadCsv: () => void;
  categoryUpdating: boolean;
  csvDownloading: boolean;
}

export function ResultsTable(props: ResultsTableProps) {
  const [category, setCategory] = useState("");

  const handleSearchSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    props.onSearchSubmit();
  };

  const handleCategorySubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!category.trim()) {
      return;
    }
    props.onAddCategory(category);
    setCategory("");
  };

  const columns = props.results?.columns ?? [];
  const rows = props.results?.results ?? [];

  return (
    <section className="results-section">
      <div className="results-header">
        <h3>Results</h3>
        <div className="results-actions">
          {props.results?.csv_url ? (
            <button
              type="button"
              className="secondary"
              onClick={props.onDownloadCsv}
              disabled={props.csvDownloading}
            >
              {props.csvDownloading ? "Preparing..." : "Download CSV"}
            </button>
          ) : null}
        </div>
      </div>

      <form className="search-form" onSubmit={handleSearchSubmit}>
        <input
          value={props.search}
          onChange={(event) => props.onSearchChange(event.target.value)}
          placeholder="Filter by word"
        />
        <button type="submit" className="secondary" disabled={props.isLoading || !props.runId}>
          Filter
        </button>
      </form>

      <div className="table-shell">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={Math.max(columns.length, 1)}>{props.isLoading ? "Loading..." : "No rows"}</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.row_index}>
                  {columns.map((column) => (
                    <td key={`${row.row_index}:${column}`}>
                      {String(row.row_data[column] ?? "")}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination">
        <button
          type="button"
          className="secondary"
          disabled={props.currentPage <= 1 || props.isLoading}
          onClick={() => props.onPageChange(props.currentPage - 1)}
        >
          Previous
        </button>
        <span>
          Page {props.currentPage} / {Math.max(props.totalPages, 1)}
        </span>
        <button
          type="button"
          className="secondary"
          disabled={props.currentPage >= props.totalPages || props.isLoading}
          onClick={() => props.onPageChange(props.currentPage + 1)}
        >
          Next
        </button>
      </div>

      <form className="category-form" onSubmit={handleCategorySubmit}>
        <label htmlFor="category-input">Add category to resulting words</label>
        <div className="category-controls">
          <input
            id="category-input"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            placeholder="HSK1"
          />
          <button type="submit" className="secondary" disabled={props.categoryUpdating || !props.runId}>
            {props.categoryUpdating ? "Applying..." : "Apply Category"}
          </button>
        </div>
      </form>
    </section>
  );
}
