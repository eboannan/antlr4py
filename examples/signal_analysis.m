% Parse this MATLAB script using grammars/matlab61.g4.
samples = [1 -2 3 .5];
signal = samples(1:end-1);
gain = @sin;
result = feval(gain, signal);
last = result(end);

if last > 0
    disp 'positive sample'
else
    disp 'nonpositive sample'
end
