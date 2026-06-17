import { Link } from "react-router-dom";

type Props = {
  size?: number;
  withWordmark?: boolean;
  /** When set, the whole mark becomes a link (e.g. "/" to return home). */
  to?: string;
};

/**
 * Brand wellness mark — the actual AcciAssist logo (four-blade pinwheel with a
 * white medical cross), extracted to a transparent PNG so it sits on any background.
 */
export function Logo({ size = 40, withWordmark = false, to }: Props) {
  const style = { display: "inline-flex", alignItems: "center", gap: 12 } as const;
  const inner = (
    <>
      <img
        src="/logo.png"
        width={size}
        height={size}
        alt="AcciAssist"
        style={{ display: "block", flex: "0 0 auto" }}
      />
      {withWordmark && (
        <span className="logo-wordmark">
          Acci<span className="logo-wordmark-accent">Assist</span>
        </span>
      )}
    </>
  );

  if (to) {
    return (
      <Link to={to} className="logo logo-link" style={style} aria-label="AcciAssist home">
        {inner}
      </Link>
    );
  }
  return (
    <span className="logo" style={style}>
      {inner}
    </span>
  );
}
