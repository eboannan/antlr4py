function [value count] = summarize(A)
persistent calls
global scale
if isempty(calls)
    calls = 0;
end
calls = calls + 1;
value = local_sum(A(:)) * scale;
count = calls;

function value = local_sum(x)
value = 0;
for k = 1:length(x)
    value = value + x(k);
end
