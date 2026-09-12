/**
 * Format number with apostrophes every 3 digits
 * Example: 1000000 -> 1'000'000
 */
export const formatNumber = (value: number, decimals: number = 2): string => {
  if (typeof value !== 'number') return '0.00';
  
  // Split into integer and decimal parts
  const [intPart, decPart] = value.toFixed(decimals).split('.');
  
  // Add apostrophes to integer part every 3 digits from the right
  const formattedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, "'");
  
  // Combine back with dot for decimals
  return `${formattedInt}.${decPart}`;
};

/**
 * Format currency with apostrophes every 3 digits
 * Example: 1000000 -> $1'000'000.00
 */
export const formatCurrency = (value: number, decimals: number = 2): string => {
  return `$${formatNumber(value, decimals)}`;
};

/**
 * Format percentage
 * Example: 1.5 -> 1.50%
 */
export const formatPercent = (value: number, decimals: number = 2): string => {
  return `${formatNumber(value, decimals)}%`;
};
