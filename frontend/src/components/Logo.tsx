type Props = {
  size?: number;
  withWordmark?: boolean;
};

/**
 * Brand wellness mark — the actual AcciAssist logo (four-blade pinwheel with a
 * white medical cross), extracted to a transparent PNG so it sits on any background.
 */
export function Logo({ size = 40, withWordmark = false }: Props) {
  return (
    <span className="logo" style={{ display: "inline-flex", alignItems: "center", gap: 12 }}>
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
    </span>
  );
}
