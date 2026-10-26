import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { MOTION } from "../shared/theme/tokens";
import { SessionControls } from "./SessionControls";
import styles from "./Shell.module.css";

const NAV = [
  { to: "/", label: "Line", end: true },
  { to: "/issues", label: "Issues" },
  { to: "/units", label: "Airframes" },
  { to: "/releases", label: "Releases" },
  { to: "/instructions", label: "Work instruction" },
];

function active(pathname: string, to: string, end?: boolean) {
  return end ? pathname === to : pathname === to || pathname.startsWith(`${to}/`);
}

export function Shell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <div className={styles.shell}>
      <a className={styles.skip} href="#main">
        Skip to content
      </a>
      <header className={styles.top}>
        <div className={styles.bar}>
          <Link to="/" className={styles.brand}>
            <span className={styles.mark} aria-hidden>
              {[0, 1, 2, 3, 4].map((i) => (
                <span key={i} />
              ))}
            </span>
            <span>
              <strong>Line software support</strong>
              <span>HX-2 VTOL, emulated line</span>
            </span>
          </Link>
          <SessionControls />
        </div>
        <nav aria-label="Main" className={styles.nav}>
          <ul>
            {NAV.map((n) => (
              <li key={n.to}>
                <NavLink to={n.to} end={n.end} className={styles.link}>
                  {n.label}
                  {active(pathname, n.to, n.end) && (
                    <motion.span
                      layoutId="nav-marker"
                      className={styles.marker}
                      transition={{ duration: MOTION.move, ease: MOTION.ease }}
                    />
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" className={styles.main}>
        {children}
      </main>
      <footer className={styles.footer}>
        The airframes, boards and modules here run on an emulated line: real firmware in QEMU, a simulated
        mission computer, and the real station software.
      </footer>
    </div>
  );
}
