# pyrigol
Class for controlling an oscilloscope (Rigol DS1054Z is author's target device)

This class uses pyVisa to control an oscilloscope in Python.  

The specific goal was to extract long records from a Rigol DS1054z, but where generality came cheap, I put it in.

Alpha level of development.  When I need a new feature, I write it and debug it to the point where it works for me.

Sample usage:
```
from rigol import Oscilloscope
import matplotlib.pyplot as plt
from time import sleep
import numpy as np

# I don't have Oscilloscope() working, so use its factory method. 
scope = Oscilloscope.getscope() 
# The argument libkey='@py' uses pyvisa-py, which doesn't seem to work very well with my code

# Use only Channel 1 on max gain
scope.channel([2,3,4], display=0)
scope.channel(1, display=1, scale=0.01, probe='10', units='volt')
# print out the current settings:
print(scope.channel([1,2,3,4],allparams=True))

# Get 12M points at 10 MS/s (1.2 seconds.  Multiply timescale=0.1 by 12 grid squares to get length)
scope.set(depth=12000000, timescale=0.1)
scope.run(single=True)
sleep(2.0)
if scope.status() != 'STOP':
    # It didn't go immediately, so force it just for the demo
    scope.run(force=True)
    sleep(2.0)
scope.stop()
# get_wave returns columns for time and all displayed channels.
# If you don't use raw, it gives you time in seconds and signals in whatever the vertical scale is.
# This can take 10s of seconds.  The screen will flash 'Can operate now!' every time it gets a chunk
wave = scope.get_wave(raw=True)[:,1]
# Let's see what the frequency content is
wave = wave - wave.mean()   # stomp on the DC offset
spect = np.log10(np.abs(np.fft.rfft(wave))) * 20   # FFT leads to the power spectrum in dB
freqs = np.fft.rfftfreq(len(wave), 1/scope.srate) # converting to frequency requires the sample rate
# 12 million real points gives 6 million frequencies.  Too many to plot, so only look at 99%ile
cliplevel = np.percentile(spect, 99)
w = spect > cliplevel
w[0:5] = False  # Stomp on the low frequencies again
plt.plot(freqs[w], spect[w])
ax = plt.gca()
ax.set(xscale='log',xlabel='Frequency (Hz)', ylabel='Power (dB)')
```



I used the National Instruments VISA libraries.  I had less luck wiht pyvisa-py (the pure python implementation).

There are hundreds of repos you find when searching for Rigol or DS1054z on Github (I refered to some of them when I wrote this.)  Some from the first page of results:

https://github.com/pklaus/ds1054z  Screen grabber.

https://github.com/wd5gnr/qrigol  Control program (complete GUI written in QT):

https://github.com/dstahlke/rigol_long_mem   Grab a waveform


# https://gist.githubusercontent.com/shirriff/bb010c7dbd7f0ce69cba/raw/15232c45aa4c7d75f4a16f09f8a98aaed235fae5/rigol-plt.py

Download data from a Rigol DS1052E oscilloscope and graph with matplotlib.
By Ken Shirriff, http://righto.com/rigol

Based on http://www.cibomahto.com/2010/04/controlling-a-rigol-oscilloscope-using-linux-and-python/
by Cibo Mahto.

Also:
https://github.com/dstahlke/rigol_long_mem/blob/master/rigol.py
