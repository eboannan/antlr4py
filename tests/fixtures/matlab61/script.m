% Representative legacy script: syntax only; no MATLAB execution is performed.
clear all
dir *.m
load measurements.mat
save -ascii backup.txt measurements
h = @sin;
A = [1 -2; 3 +4];
C = {'label' A; 'samples' [.5 1. 2e-3]};
s.samples = C{2,2};
x = s.samples(1:end-1);
y = feval(h, x) + ...
    2.*x.^2;
for k = 1:length(y)
    if y(k) < 0
        continue;
    end
    switch k
    case 1
        disp 'first sample'
    otherwise
        try
            disp(y(k));
        catch
            break;
        end
    end
end
