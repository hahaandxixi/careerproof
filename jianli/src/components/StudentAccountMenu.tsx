"use client";
import AccountMenu, { type AccountMenuProps } from "./AccountMenu";
export default function StudentAccountMenu(props: AccountMenuProps) {
  return <AccountMenu {...props} role="student" />;
}
