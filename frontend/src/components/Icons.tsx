import type { SVGProps } from 'react';

type IconProps = SVGProps<SVGSVGElement>;

function BaseIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 20 20"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    />
  );
}

export function RefreshIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M16.5 10a6.5 6.5 0 1 1-1.9-4.6" />
      <path d="M16.5 3.8v3.9h-3.9" />
    </BaseIcon>
  );
}

export function ReindexIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M3.5 10a6.5 6.5 0 0 1 11.1-4.6" />
      <path d="M14.6 1.8v3.9h-3.9" />
      <path d="M16.5 10a6.5 6.5 0 0 1-11.1 4.6" />
      <path d="M5.4 18.2v-3.9h3.9" />
    </BaseIcon>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 5.2h12" />
      <path d="M7.2 5.2V3.4h5.6v1.8" />
      <path d="M5.8 5.2l.8 11h6.8l.8-11" />
      <path d="M8.1 8v5.2" />
      <path d="M11.9 8v5.2" />
    </BaseIcon>
  );
}

export function EditIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M3.7 16.3l3.1-.7 8-8a1.6 1.6 0 0 0-2.3-2.3l-8 8-.8 3z" />
      <path d="M11.7 4.7l3.6 3.6" />
    </BaseIcon>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4.5 3.5h7a2 2 0 0 1 2 2v11h-7a2 2 0 0 0-2 2z" />
      <path d="M13.5 5.5h1a1 1 0 0 1 1 1v10" />
      <path d="M6.5 6.5h5" />
      <path d="M6.5 9.5h5" />
    </BaseIcon>
  );
}

export function ChatBubbleIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 5.5a2.5 2.5 0 0 1 2.5-2.5h7A2.5 2.5 0 0 1 16 5.5v5A2.5 2.5 0 0 1 13.5 13H9l-3.5 3v-3H6.5A2.5 2.5 0 0 1 4 10.5z" />
    </BaseIcon>
  );
}

export function SlidersIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4 5h12" />
      <circle cx="8" cy="5" r="1.7" />
      <path d="M4 10h12" />
      <circle cx="12" cy="10" r="1.7" />
      <path d="M4 15h12" />
      <circle cx="6.5" cy="15" r="1.7" />
    </BaseIcon>
  );
}

export function SystemIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="10" cy="10" r="2.2" />
      <path d="M10 2.8v2.1" />
      <path d="M10 15.1v2.1" />
      <path d="M17.2 10h-2.1" />
      <path d="M4.9 10H2.8" />
      <path d="M15.1 4.9l-1.5 1.5" />
      <path d="M6.4 13.6l-1.5 1.5" />
      <path d="M15.1 15.1l-1.5-1.5" />
      <path d="M6.4 6.4L4.9 4.9" />
    </BaseIcon>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <circle cx="10" cy="6.3" r="2.6" />
      <path d="M4.6 16.2a5.7 5.7 0 0 1 10.8 0" />
    </BaseIcon>
  );
}

export function BotIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <rect x="4.2" y="6.2" width="11.6" height="8.4" rx="2" />
      <path d="M10 3v3.2" />
      <circle cx="7.6" cy="10.3" r="0.7" fill="currentColor" stroke="none" />
      <circle cx="12.4" cy="10.3" r="0.7" fill="currentColor" stroke="none" />
      <path d="M8 12.5h4" />
    </BaseIcon>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M4.5 10.2l3.2 3.2 7.8-7.8" />
    </BaseIcon>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <BaseIcon {...props}>
      <path d="M5 5l10 10" />
      <path d="M15 5L5 15" />
    </BaseIcon>
  );
}
