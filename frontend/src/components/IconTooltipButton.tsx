import { Button, Tooltip } from 'antd';
import type { ButtonProps, TooltipProps } from 'antd';
import type { ReactNode } from 'react';

interface IconTooltipButtonProps extends Omit<ButtonProps, 'aria-label' | 'icon' | 'title'> {
  label: string;
  icon: ReactNode;
  placement?: TooltipProps['placement'];
}

export function IconTooltipButton({ label, icon, placement, ...buttonProps }: IconTooltipButtonProps) {
  return (
    <Tooltip title={label} placement={placement}>
      <Button aria-label={label} icon={icon} {...buttonProps} />
    </Tooltip>
  );
}
