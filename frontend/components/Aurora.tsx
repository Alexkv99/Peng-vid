import React from "react";

type AuroraProps = {
  colorStops: string[];
  blend?: number;
  amplitude?: number;
  speed?: number;
};

const Aurora = ({ colorStops, blend = 0.5 }: AuroraProps) => {
  const gradient = `linear-gradient(120deg, ${colorStops.join(", ")})`;
  const overlay = `radial-gradient(circle at 20% 20%, rgba(255,255,255,${blend}), transparent 55%)`;

  return (
    <div
      aria-hidden="true"
      className="h-full w-full"
      style={{
        backgroundImage: `${overlay}, ${gradient}`,
        filter: "blur(60px)",
        opacity: 0.9,
      }}
    />
  );
};

export default Aurora;
