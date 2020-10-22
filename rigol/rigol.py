#! /Users/palmer/anaconda/envs/oscope/bin/python


"""

"""
from tempfile import mkstemp

import numpy as np
import sys
import pyvisa
from time import sleep
from datetime import datetime, timedelta


class Oscilloscope(pyvisa.resources.usb.USBInstrument):
    libkey = ''  # or '@py'
    allchans = list(range(1, 5))  # 1..4
    channelparams = "BWLimit,COUPling,DISPlay,INVert,OFFSet,RANGe,TCAL,SCALe,PROBe,UNITs,VERNier".split(",")
    headersize = 11
    chunkpoints = 250000  # 250000   # Up to 250,000 , but that times out

    def _get_wave_parameters(self, channel):
        self.write(f":WAV:SOUR CHAN{channel}")
        self.write(':WAV:PRE?')
        preamble = self.read_raw()
        (self.wav_format, self.wav_type, self.wav_points, self.wav_count,
         self.wav_xincrement, self.wav_xorigin, self.wav_xreference,
         self.wav_yincrement, self.wav_yorigin, self.wav_yreference
         ) = [float(f) for f in preamble.split(b'\n')[0].split(b',')[:10]]
        self.wav_points = int(self.wav_points)
        self.trigpos = int(self.query_ascii_values(f":TRIG:POS?")[0])
        self.timescale = self.query_ascii_values(":TIM:SCAL?")[0]

        # Get the timescale offset
        self.timeoffset = self.query_ascii_values(":TIM:OFFS?")[0]
        self.voltscale = self.query_ascii_values(f':CHAN{channel}:SCAL?')[0]

        # And the voltage offset
        self.voltoffset = self.query_ascii_values(f":CHAN{channel}:OFFS?")[0]

    def wait_for_trigger(self, timeout=None, sleep_increment=0.1):
        """

        :param timeout: None: don't timeout, otherwise seconds
        :return: True if currently triggered, else False
        :param sleep_increment: How long to sleep (seconds) each wait cycle
        """
        tstart = datetime.utcnow()
        sleep(0.1)
        while int(self.query_ascii_values(f":TRIG:POS?")[0]) == -2:
            if timeout is not None:
                if (datetime.utcnow() - tstart).total_seconds() > timeout:
                    return False
            sleep(sleep_increment)
        return True

    def status(self):
        return self.query_ascii_values(":TRIG:STAT?", converter='s')[0].strip()

    def stop(self):
        self.write(":STOP")
        while self.status() != 'STOP':
            sleep(0.5)

    def clear(self):
        self.write(":CLEAR")
        sleep(0.5)
        try:
            self.read_raw()
        except Exception:
            pass

    def run(self, single=False, force=False, wait=False):
        run = True
        if single:
            self.write(":SING")
            run = False
        if force:
            if not run:
                # Just sent a command, so pause for next
                sleep(1.0)
            self.write(":TFORCE")
            run = False
        if run:
            self.write(":RUN")
        if wait:
            timeout = None if wait is True else float(wait)
            self.wait_for_trigger(timeout=timeout)

    def channel(self, channel, allparams=False, **kwargs):
        """
        Set channel parameters

        If a parameter has None then it is not set, but is read back
        See programming guide
        :param channel: 1..4 or Iterable[1..4]
        :param kwargs: [BWLimit, COUPling, DISPlay, INVert, OFFSet, RANGe, TCAL, SCALe, PROBe, UNITs, VERNier]
        :param allparams: # Return all parameters
        :return: parameter readback
        """
        result = {}
        if not np.isscalar(channel):
            for chan in channel:
                result[f"CHAN{chan}"] = self.channel(channel=chan, allparams=allparams, **kwargs)
            return result
        if allparams:
            for param in self.channelparams:
                for key in kwargs.keys():
                    if param.lower().startswith(key.lower()):
                        break
                else:
                    kwargs[param] = None
        for key, value in kwargs.items():
            if value is not None:
                self.write(f":CHAN{channel}:{key} {value}")
            result[key] = self.query_ascii_values(f":CHAN{channel}:{key}?", converter='s')[0].strip()
        return result

    def setup(self, setup=None):
        if setup == None:
            self.write(":SYSTem:SETup?")
            setup = self.read_rawblock()
            return setup
        else:
            setupblock = bytes(f"#9{len(setup):09d}", 'utf-8')+setup
            self.write_raw(b":SYSTem:SETup "+setupblock)

    def set(self, all=False, **kwargs):
        """
        :param depth:  {AUTO|12000|120000|1200000|12000000|24000000}
        :param timescale: {1,2,5}e{-9..1}
        :param kwargs:
        :return:
        """
        settings = {'timeoffset': ':TIMEBASE:OFFS',
                    'timescale': ':TIMEBASE:SCAL',
                    'timedelayenable': ':TIMEBASE:DELAY:ENABLE',
                    'timedelayoffset': ':TIMEBASE:DELAY:OFFSET',
                    'timedelayscale': ':TIMEBASE:DELAY:SCALE',
                    'depth': ':ACQ:MDEPTH',}
        result = {}
        if all:
            for k in settings.keys():
                kwargs.setdefault(k, None)
        for k,v in kwargs.items():
            if v != None:
                self.write(f"{settings[k]} {v}")
            result[k] = self.query(f"{settings[k]}?").strip()
        return result


    @property
    def error(self):
        return self.query(":SYST:ERR?")

    @property
    def srate(self):
        """
        Sample rate
        :return:
        """
        return self.query_ascii_values(':ACQUIRE:SRATE?')[0]

    @property
    def nchannels(self):
        """
        Number of (analog) channels
        :return:
        """
        if not hasattr(self, "_nchannels"):
            self._nchannels = int(self.query_ascii_values(":SYSTEM:RAM?")[0])
        return self._nchannels

    def get_channels(self):
        """
        Get currently displayed channels
        :return: [chans,]    range 1..4
        """
        result = [chan for chan in range(1,self.nchannels + 1) if
                  self.query_ascii_values(f":CHAN{chan}:DISP?")[0] == 1]
        return result

    def _prepare_waveread(self, channel):
        self.write(":WAV:MODE RAW")
        self.write(":WAV:FORM BYTE")
        self._get_wave_parameters(channel)

    def get_wave(self, channels=None, trange=None, raw=False):
        if channels is None:
            channels = self.get_channels()
        if np.isscalar(channels):
            channels = [channels]
        for chan in channels:
            self._prepare_waveread(chan)
            try:
                id(irange)
            except NameError:
                # irange is zero-based and exclusive of upper limit
                try:
                    irange = np.clip([self.trigpos + (t / self.wav_xincrement)
                                      for t in trange], 0, self.wav_points).astype(int)
                except:
                    irange = np.array([0, self.wav_points])
                if raw:
                    tvals = np.arange(*irange)
                else:
                    # tvals = (np.arange(*irange) - self.trigpos) * self.wav_xincrement
                    tvals = (np.arange(*irange) * self.wav_xincrement) + self.wav_xorigin
                result = [tvals]
            # Read chunk by chunk
            data = []
            for istart in range(irange[0], irange[1], self.chunkpoints):
                self.write(f":WAV:STAR {istart + 1}")
                iend = min(istart + self.chunkpoints, irange[1])
                self.write(f":WAV:STOP {iend}")
                try:
                    self.write(":WAV:DATA?")
                    rawdata = self.read_rawblock()
                    if len(rawdata) != (iend - istart):
                        raise RuntimeError("Not correct number of bytes")
                    data.extend(rawdata)
                    # rawdata = self.query_binary_values(f":WAV:DATA?", datatype='B', header_fmt='empty',
                    #                                    data_points=iend - istart + self.headersize)
                    # data.extend(rawdata[self.headersize:])
                except Exception as e:
                    print(e)
                    pass
            if raw:
                result.append(data)
            else:
                scaledata = (np.asarray(data, dtype=float)
                             - (self.wav_yorigin + self.wav_yreference)
                             ) * self.wav_yincrement
                result.append(scaledata)
        return np.vstack(result).transpose()

    def screenshot(self, filename=None, format=None, asbytes=False, color="ON", invert="OFF"):
        """
        Take oscilloscope screenshot

        :param filename:
        :param format:{BMP24|BMP8|PNG|JPEG|TIFF}
        :param color: {{1|ON}|{0|OFF}}
        :param invert: {ON|OFF}
        :param asbytes: default false
        :return: filename or (if asbytes) bytes of the image in the given format
        """
        if format is None:
            if filename is not None:
                format = str(filename).rsplit('.', 1)[-1]
            else:
                format = ""   #   Let scope decide
        self.write(f":DISP:DATA? {color},{invert},{format}")
        data = self.read_rawblock()
        if asbytes:
            return data
        else:
            if filename is None:
                file = mkstemp(suffix=format.lower())
            else:
                file = open(filename, "wb")
            file.write(data)
            return file.name

    def read_rawblock(self):
        """
        Read raw data from oscilloscope in form:
        #NXXX...XXXBBBBBBB...
        Where # is '#', N is '0'..'9', XXXX...XXX is the N digit number of bytes, and BB.. is the bytes
        :return: the bytes
        """
        bytesin = self.read_raw()
        if len(bytesin) < 2 or bytesin[0:1] != b'#' or not b'0' <= bytesin[1:2] <= b'9':
            raise RuntimeError("Header not found")
        n_digits = int(bytesin[1:2])
        n_bytes, data = int(bytesin[2:2 + n_digits]), bytesin[2 + n_digits:]
        while len(data) < n_bytes:
            try:
                data += self.read_raw()
            except pyvisa.errors.VisaIOError as e:
                sleep(max(self.query_delay, 0.01))
                data += self.read_raw()
        if len(data) > n_bytes:
            # The RigolDS1054z scope likes to append byte(10) = \n even to byte data
            data = data[:n_bytes]
        return data

    @classmethod
    def getscope(cls, startswith='USB', libkey=None):
        # Get the USB device, e.g. 'USB0::0x1AB1::0x0588::DS1ED141904883'
        rm = pyvisa.ResourceManager(cls.libkey if libkey is None else libkey)
        instruments = [key for key in rm.list_resources(query=startswith + "?*::INSTR") if key.startswith(startswith)]
        if len(instruments) != 1:
            print('Bad instrument list', instruments)
            sys.exit(-1)
        # timeout in ms, query_delay in s
        scope = rm.open_resource(instruments[0], resource_pyclass=cls, timeout=2000, chunk_size=1024000,
                                 query_delay=0.2)  # bigger timeout for long mem
        return scope
