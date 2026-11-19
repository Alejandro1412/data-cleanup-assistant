interface Props {
  value: string | null;
  variant?: "plain" | "removed" | "added";
}

/**
 * Renders a cell value with its whitespace made visible. Trailing spaces and
 * empty strings are real data problems, and they are invisible in normal text.
 */
export function CellValue({ value, variant = "plain" }: Props) {
  if (value === null || value === "") {
    return <span className={`cell cell--${variant} cell--empty`}>empty</span>;
  }
  const parts = value.split(/( )/);
  return (
    <span className={`cell cell--${variant}`}>
      <span aria-hidden="true">
        {parts.map((part, index) =>
          part === " " ? (
            <span key={index} className="cell__space">
              ·
            </span>
          ) : (
            part
          ),
        )}
      </span>
      <span className="visually-hidden">{value}</span>
    </span>
  );
}
