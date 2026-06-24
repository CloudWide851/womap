import { Button, Tooltip } from 'antd';
import type { ButtonProps } from 'antd';
import type { ReactNode } from 'react';

interface IconTooltipButtonProps extends Omit<ButtonProps, 'aria-label' | 'icon' | 'title'> {
  label: string;
  icon: ReactNode;
}

export function IconTooltipButton({ label, icon, ...buttonProps }: IconTooltipButtonProps) {
  return (
    <Tooltip title={label}>
      <Button aria-label={label} icon={icon} {...buttonProps} />
    </Tooltip>
  );
}
