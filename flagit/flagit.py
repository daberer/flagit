"""
Created on March 19, 2020

@author: Daniel Aberer daniel.aberer@geo.tuwien.ac.at

"""

import pandas as pd
import numpy as np
from scipy.signal import savgol_filter as savgol


def flagit(df):
    flag_c01(df)
    flag_c02(df)
    flag_c03(df)
    flag_d01(df)
    flag_d02(df)
    flag_d03(df)  # D5 included
    flag_d04(df)
    flag_d05(df)
    flag_d06(df)
    # flag_d07(df)  # D8 included
    # flag_d09(df)
    # flag_d10(df)
    # flag_g(df)
    return df


def apply_savgol(df):
    """
    Calculates derivations 1 and 2 using Savitzky-Golay filer
    """
    df['deriv1'] = savgol(df.soil_moisture, 3, 2, 1, mode='nearest')
    df['deriv2'] = savgol(df.soil_moisture, 3, 2, 2, mode='nearest')


def flag_c01(df):
    """
    Lower Boundary - flags when measurement is below threshold
    """
    low_boundary = 0
    index = df[df.soil_moisture < low_boundary].index
    if len(index):
        df.qflag[index].apply(lambda x: x.add(1))


def flag_c02(df):
    """
    Upper Boundary - flags when measurement is above threshold
    """
    upper_boundary = 60
    index = df[df.soil_moisture > upper_boundary].index
    if len(index):
        df.qflag[index].apply(lambda x: x.add(2))


def flag_c03(df, hwsd=None):
    """
    HWSD Saturation Point - flags when measurment is above saturation point (at the station location)
    """
    if not hwsd:
        return

    index = df.loc[df.soil_moisture > hwsd].index
    if len(index):
        df.qflag[index].apply(lambda x: x.add(3))


def flag_d01(df):
    """
    In situ Soil Temperature - flags when in situ soil temperature is below 0 degrees celsius

    """
    if 'soil_temperature' in df.columns:
        index = df[df.soil_temperature < 0].index
        if len(index):
            df.qflag[index].apply(lambda x: x.add(4))


def flag_d02(df):
    """
    In situ Air Temperature - flags when in situ air temperature is below 0 degrees celsius

    """
    if 'air_temperature' in df.columns:
        index = df[df['air_temperature'] < 0].index
        if len(index):
            df.qflag[index].apply(lambda x: x.add(5))


def flag_d03(df):
    """
    Gldas soil temperature

    """
    if 'gldas_soil_temperature' in df.columns:
        index = df[df['gldas_soil_temperature'] < 0].index
        if len(index):
            df.qflag[index].apply(lambda x: x.add(6))


def flag_d04(df):
    """
    This flag was designed for surface soil moisture, sensors at depths greater than 10cm behave differently.

    If soil moisture shows rise without insitu precipitation event in the preceding 24h.
    through resampling nan values are added to fill gaps in the sm and p timeseries.
    this is important for the calculation of the std-dev and the rise of sm, and the sum of 24h precipitation.
    if there is an hourly rise in sm, a rise within the last 24h that is larger than twice the std-dev of sm and there
    is no precipitation event greater or equal to the minimum precipitation (dependent on depth of sensor),
    then a measurement is flagged.
    """
    if 'precipitation' in df.columns:
        min_precipitation = 0.2

        df['std_x2'] = df['soil_moisture'].rolling(min_periods=1, window=25).std() * 2
        df['rise24h'] = df['soil_moisture'].diff(24)
        df['rise1h'] = df['soil_moisture'].diff(1)

        index = df[(df['rise1h'] > 0) & (df['rise24h'] > df['std_x2']) & 
                   (df['precipitation'] < min_precipitation)].index

        df.qflag[index].apply(lambda x: x.add(7))


def flag_d05(df):
    """
    Should only be applied to surface soil moisture sensors (<= 10cm sensor depth)
    :param df:
    :return:
    """
    # flag D05

    if 'gldas_precipitation' in df.columns:
        min_precipitation = 0.2

        df['gl_std_x2'] = df['soil_moisture'].rolling(min_periods=1,
                                                            window=25).std() * 2
        df['gl_rise24h'] = df['soil_moisture'].diff(24)
        df['gl_rise1h'] = df['soil_moisture'].diff(1)
        df['gldas_precipitation_total'] = df['gldas_precipitation'].rolling(min_periods=1, window=24).sum()

        index = df[(df['gl_rise1h'] > 0) & (df['gl_rise24h'] > df['gl_std_x2']) &
                   (df['gldas_precipitation_total'] < min_precipitation)].index

        if len(index):
            df.qflag[index].apply(lambda x: x.add(8))


def flag_d06(df):
    """
    Checks if time-series shows a spike.

    Criteria
    --------
    1. rise or fall of 15%
    2. ratio of second derivates of t-1 and t+1 respectively is between 0.8 and 1.2
    3. variance to mean ratio of observations (t-12 to t+12 without t) smaller than 1
    4. observation is positive or negative peak (t-1 to t+1)
    pandas internal functions such as rolling and shift are used to calculate the criteria, next the indices of the
    observations that fulfill these criteria are found (index), and the dataframe is flagged at these instances.
    5. additional criteria drop to zero with a delta of 5
    """

    def rolling_var(x):
        """
        returns variance of x(t-12, x+12) without the current value
        """
        x = np.delete(x, (12), axis=0)
        x = x[~np.isnan(x)]
        return ((x - x.mean()) ** 2).sum() / (len(x) - 1)

    def peak(x):
        """
        check if middle element is a positive or negative peak
        """
        if ((x[0] < x[1]) & (x[1] > x[2])) | (
                (x[0] > x[1]) & (x[1] < x[2])):  # changed to not include equal 10.7.2019
            return 1
        elif len(x) > 3:  # Added October 2019 - detect spikes that last 2 hours
            if ((x[0] < x[1]) & (x[1] == x[2]) & (x[2] > x[3])) | (
                    (x[0] > x[1]) & (x[1] == x[2]) & (x[2] < x[3])):
                return 2
        return 0

    window = np.ones(25)
    window[12] = 0  # set the center-value to zero

    df['criteria1'] = round(df['soil_moisture'].shift(-1).div(df['soil_moisture'], axis=0).shift(1), 3)
    df['criteria2'] = round(abs(
        df.deriv2.div(df['deriv2'].shift(-2), axis=0).shift(1)), 3)
    # calculate variation coefficient without value at t:
    df['criteria3'] = abs(
        df['soil_moisture'].rolling(min_periods=25, window=25, center=True).apply(rolling_var, raw=True)).div(
        df['soil_moisture'].rolling(window=window, win_type='boxcar', center=True).mean(), axis=0)
    df['criteria4'] = df['soil_moisture'].rolling(min_periods=3, window=4, center=True).apply(peak,
                                                                                                    raw=True).shift(-1)
    df['spike_2h'] = df.criteria4.shift(1) > 1.1

    df['spike'] = (((df.criteria1 > 1.15) | (df.criteria1 < 0.85)) | (df.spike_2h > 0)) & \
                         ((df.criteria2 > 0.8) & (df.criteria2 < 1.2)) & (df.criteria3 < 1) & (
                                     df.criteria4 > 0)

    index = df[(df.spike > 0) | (
                (df.spike.shift(1) > 0) & (df.spike_2h > 0))].index  # last expression for 2h spikes

    df.qflag[index].apply(lambda x: x.add(9))
        

if __name__ == '__main__':
    dataframe = pd.read_pickle('df_v2.pkl')
    dataframe_flagged = flagit(dataframe)