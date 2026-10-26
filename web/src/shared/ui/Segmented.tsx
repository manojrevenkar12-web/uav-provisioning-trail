import { motion } from "framer-motion";
import { useId } from "react";

import { MOTION } from "../theme/tokens";
import styles from "./Segmented.module.css";

/** A choice between a few views of the same thing, as radio buttons; the marker slides to the choice. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  const name = useId();
  return (
    <fieldset className={styles.group}>
      <legend className="visually-hidden">{label}</legend>
      {options.map((o) => (
        <label key={o.value} className={styles.option}>
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
          />
          {value === o.value && (
            <motion.span
              layoutId={`${name}-marker`}
              className={styles.marker}
              transition={{ duration: MOTION.move, ease: MOTION.ease }}
            />
          )}
          <span className={styles.text}>{o.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
