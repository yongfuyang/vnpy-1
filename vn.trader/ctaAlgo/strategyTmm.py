# encoding: UTF-8

"""
一个ATR-RSI指标结合的交易策略，适合用在股指的1分钟和5分钟线上。
注意事项：
1. 作者不对交易盈利做任何保证，策略代码仅供参考
2. 本策略需要用到talib，没有安装的用户请先参考www.vnpy.org上的教程安装
3. 将IF0000_1min.csv用ctaHistoryData.py导入MongoDB后，直接运行本文件即可回测策略
"""


from ctaBase import *
from ctaTemplate import CtaTemplate

import talib
import numpy as np


########################################################################
class AtrRsiStrategy(CtaTemplate):
    """结合ATR和RSI指标的一个分钟线交易策略"""
    className = 'AtrRsiStrategy'
    author = u'用Python的交易员'

    # 策略参数
    atrLength = 22          # 计算ATR指标的窗口数
    atrMaLength = 10        # 计算ATR均线的窗口数
    rsiLength = 5           # 计算RSI的窗口数
    rsiEntry = 16           # RSI的开仓信号
    trailingPercent = 1.0   # 百分比移动止损
    initDays = 10           # 初始化数据所用的天数
    fixedSize = 1           # risk
    useTrailingStop = False # 是否使用跟踪止损
    profitLock = 30         # 利润锁定
    trailingStop = 20       # 跟踪止损

    # 策略变量
    bar = None                  # K线对象
    barMinute = EMPTY_STRING    # K线当前的分钟

    bufferSize = 100                    # 需要缓存的数据的大小
    bufferCount = 0                     # 目前已经缓存了的数据的计数
    highArray = np.zeros(bufferSize)    # K线最高价的数组
    lowArray = np.zeros(bufferSize)     # K线最低价的数组
    closeArray = np.zeros(bufferSize)   # K线收盘价的数组
    openArray = np.zeros(bufferSize)    # K线开盘价的数组
                                        # Tmm K线
    H1Array = np.zeros(bufferSize)      # K线最高价的数组
    L1Array = np.zeros(bufferSize)      # K线最低价的数组
    C1Array = np.zeros(bufferSize)      # K线收盘价的数组
    O1Array = np.zeros(bufferSize)      # K线开盘价的数组
    UPorDOWNArray = np.zeros(bufferCount)

    atrCount = 0                        # 目前已经缓存了的ATR的计数
    atrArray = np.zeros(bufferSize)     # ATR指标的数组
    atrValue = 0                        # 最新的ATR指标数值
    atrMa = 0                           # ATR移动平均的数值

    rsiValue = 0                        # RSI指标的数值
    rsiBuy = 0                          # RSI买开阈值
    rsiSell = 0                         # RSI卖开阈值
    intraTradeHigh = 0                  # 移动止损用的持仓期内最高价
    intraTradeLow = 0                   # 移动止损用的持仓期内最低价

    orderList = []                      # 保存委托代码的列表



    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'atrLength',
                 'atrMaLength',
                 'rsiLength',
                 'rsiEntry',
                 'trailingPercent']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos',

               'atrValue',
               'atrMa',
               'rsiValue',
               'rsiBuy',
               'rsiSell']

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(AtrRsiStrategy, self).__init__(ctaEngine, setting)

        # 注意策略类中的可变对象属性（通常是list和dict等），在策略初始化时需要重新创建，
        # 否则会出现多个策略实例之间数据共享的情况，有可能导致潜在的策略逻辑错误风险，
        # 策略类中的这些可变对象属性可以选择不写，全都放在__init__下面，写主要是为了阅读
        # 策略时方便（更多是个编程习惯的选择）


        self.isPrePosHaved = False
        self.isAlreadyTraded = False

    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' %self.name)

        # 初始化RSI入场阈值
        self.rsiBuy = 50 + self.rsiEntry
        self.rsiSell = 50 - self.rsiEntry

        # 载入历史数据，并采用回放计算的方式初始化策略数值
        initData = self.loadBar(self.initDays)
        for bar in initData:
            self.onBar(bar)

        self.putEvent()

    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' %self.name)
        self.putEvent()

    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' %self.name)
        self.putEvent()

    #----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        # 计算K线
        tickMinute = tick.datetime.minute

        if tickMinute != self.barMinute:
            if self.bar:
                self.onBar(self.bar)

            bar = CtaBarData()
            bar.vtSymbol = tick.vtSymbol
            bar.symbol = tick.symbol
            bar.exchange = tick.exchange

            bar.open = tick.lastPrice
            bar.high = tick.lastPrice
            bar.low = tick.lastPrice
            bar.close = tick.lastPrice

            bar.date = tick.date
            bar.time = tick.time
            bar.datetime = tick.datetime    # K线的时间设为第一个Tick的时间

            self.bar = bar                  # 这种写法为了减少一层访问，加快速度
            self.barMinute = tickMinute     # 更新当前的分钟
        else:                               # 否则继续累加新的K线
            bar = self.bar                  # 写法同样为了加快速度

            bar.high = max(bar.high, tick.lastPrice)
            bar.low = min(bar.low, tick.lastPrice)
            bar.close = tick.lastPrice

    #----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # 撤销之前发出的尚未成交的委托（包括限价单和停止单）
        for orderID in self.orderList:
            self.cancelOrder(orderID)
        self.orderList = []

        # 保存K线数据
        self.closeArray[0:self.bufferSize-1] = self.closeArray[1:self.bufferSize]
        self.highArray[0:self.bufferSize-1] = self.highArray[1:self.bufferSize]
        self.lowArray[0:self.bufferSize-1] = self.lowArray[1:self.bufferSize]
        self.openArray[0:self.bufferSize - 1] = self.openArray[1:self.bufferSize]

        self.C1Array[0:self.bufferSize - 1] = self.C1Array[1:self.bufferSize]
        self.H1Array[0:self.bufferSize - 1] = self.H1Array[1:self.bufferSize]
        self.L1Array[0:self.bufferSize - 1] = self.L1Array[1:self.bufferSize]
        self.O1Array[0:self.bufferSize - 1] = self.O1Array[1:self.bufferSize]
        self.UPorDOWNArray[0:self.bufferSize - 1] = self.UPorDOWNArray[1:self.bufferSize]

        self.closeArray[-1] = bar.close
        self.highArray[-1] = bar.high
        self.lowArray[-1] = bar.low
        self.openArray[-1] = bar.open

        self.bufferCount += 1

        if self.bufferCount == 1: #第一天特殊处理

            if self.closeArray[-1] >= self.openArray[-1]:   #上涨
                self.O1Array[-1] = self.openArray[-1]
                self.L1Array[-1] = self.openArray[-1]
                self.H1Array[-1] = self.closeArray[-1]
                self.C1Array[-1] = self.closeArray[-1]
                self.UPorDOWNArray[-1] = 1
            else:                                           #下跌
                self.O1Array[-1] = self.openArray[-1]
                self.H1Array[-1] = self.openArray[-1]
                self.L1Array[-1] = self.closeArray[-1]
                self.C1Array[-1] = self.closeArray[-1]
                self.UPorDOWNArray[-1] = 0

            pass

        if self.UPorDOWNArray[-2] == 1:                     #昨天是上涨

            if self.closeArray[-1] > self.H1Array[-2]:      #第一种情况，上涨：今天的收盘价超过前一个柱子的最高点

                self.O1Array[-1] = self.H1Array[-2]
                self.L1Array[-1] = self.H1Array[-2]
                self.H1Array[-1] = self.closeArray[-1]
                self.C1Array[-1] = self.closeArray[-1]
                self.UPorDOWNArray[-1] = 1

            if self.closeArray[-1] < self.L1Array[-2]:      #第二种情况，下跌：今天的收盘价，下跌超过前三个柱子的最低价
                a = -2                                      #低过前一个柱子的最低价，才开始计算
                hh = self.L1Array[-2]
                n = 1
                a = a - 1
                while a > -self.bufferCount - 1 :
                    if self.UPorDOWNArray[a] == 0:break

                    if self.H1Array[a] != self.H1Array[a-1]:
                        n = n + 1;
                        hh = self.L1Array[a]

                    if n == 3: break
                    a = a - 1
                if self.closeArray[-1] < hh:
                    self.O1Array[-1] = self.L1Array[-2]
                    self.H1Array[-1] = self.L1Array[-2]
                    self.L1Array[-1] = self.closeArray[-1]
                    self.C1Array[-1] = self.closeArray[-1]
                    self.UPorDOWNArray[-1] = 0


        if self.bufferCount < self.bufferSize:
            return

        # 计算指标数值
        self.atrValue = talib.ATR(self.highArray,
                                  self.lowArray,
                                  self.closeArray,
                                  self.atrLength)[-1]
        self.atrArray[0:self.bufferSize-1] = self.atrArray[1:self.bufferSize]
        self.atrArray[-1] = self.atrValue

        self.atrCount += 1
        if self.atrCount < self.bufferSize:
            return

        self.atrMa = talib.MA(self.atrArray,
                              self.atrMaLength)[-1]
        self.rsiValue = talib.RSI(self.closeArray,
                                  self.rsiLength)[-1]

        # 判断是否要进行交易

        # 当前无仓位
        if self.pos == 0:
            self.intraTradeHigh = bar.high
            self.intraTradeLow = bar.low

            # ATR数值上穿其移动平均线，说明行情短期内波动加大
            # 即处于趋势的概率较大，适合CTA开仓
            if self.atrValue > self.atrMa:
                # 使用RSI指标的趋势行情时，会在超买超卖区钝化特征，作为开仓信号
                if self.rsiValue > self.rsiBuy:
                    # 这里为了保证成交，选择超价5个整指数点下单
                    self.buy(bar.close+5, self.fixedSize)

                elif self.rsiValue < self.rsiSell:
                    self.short(bar.close-5, self.fixedSize)

        # 持有多头仓位
        elif self.pos == 1:
            # 计算多头持有期内的最高价，以及重置最低价
            self.intraTradeHigh = max(self.intraTradeHigh, bar.high)
            self.intraTradeLow = bar.low
            # 计算多头移动止损
            longStop = self.intraTradeHigh * (1-self.trailingPercent/100)
            # 发出本地止损委托，并且把委托号记录下来，用于后续撤单
            orderID = self.sell(longStop, abs(self.pos), stop=True)
            self.orderList.append(orderID)

        # 持有空头仓位
        elif self.pos == -1:
            self.intraTradeLow = min(self.intraTradeLow, bar.low)
            self.intraTradeHigh = bar.high

            shortStop = self.intraTradeLow * (1+self.trailingPercent/100)
            orderID = self.cover(shortStop, abs(self.pos), stop=True)
            self.orderList.append(orderID)

        # 发出状态更新事件
        self.putEvent()


    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        pass

    #----------------------------------------------------------------------
    def onTrade(self, trade):
        pass

    #----------------------------------------------------------------------
    def onPosition(self, pos):

        if  self.isPrePosHaved  or self.isAlreadyTraded:         # 还没有开过仓，或，还没有获取历史仓位
            return
        elif pos.position != 0:
            if pos.direction == DIRECTION_LONG:
                self.pos = pos.position
            else:
                self.pos = -1 * pos.position
            self.lastEntryPrice = pos.price
            self.isPrePosHaved = True

        #print  (u'{0} {1}  历史持仓 {2}  开仓均价 {3}'.format(datetime.now(), self.vtSymbol, self.pos, pos.price))
        #pass


if __name__ == '__main__':
    # 提供直接双击回测的功能
    # 导入PyQt4的包是为了保证matplotlib使用PyQt4而不是PySide，防止初始化出错
    from ctaBacktesting import *
    from PyQt4 import QtCore, QtGui

    # 创建回测引擎
    engine = BacktestingEngine()

    # 设置引擎的回测模式为K线
    engine.setBacktestingMode(engine.BAR_MODE)

    # 设置回测用的数据起始日期
    engine.setStartDate('20161010')

    # 设置产品相关参数
    engine.setSlippage(0.2)  # 股指1跳
    engine.setRate(0.3 / 10000)  # 万0.3
    engine.setSize(15)  # 股指合约大小

    # 设置使用的历史数据库
    engine.setDatabase(MINUTE_DB_NAME, 'ag1612')

    ## 在引擎中创建策略对象
    # d = {'atrLength': 11}
    # engine.initStrategy(AtrRsiStrategy, d)

    ## 开始跑回测
    ##engine.runBacktesting()

    ## 显示回测结果
    ##engine.showBacktestingResult()

    # 跑优化
    setting = OptimizationSetting()  # 新建一个优化任务设置对象
    setting.setOptimizeTarget('capital')  # 设置优化排序的目标是策略净盈利
    setting.addParameter('atrLength', 11, 20, 1)  # 增加第一个优化参数atrLength，起始11，结束12，步进1
    setting.addParameter('atrMaLength', 20, 30, 5)  # 增加第二个优化参数atrMa，起始20，结束30，步进1

    # 性能测试环境：I7-3770，主频3.4G, 8核心，内存16G，Windows 7 专业版
    # 测试时还跑着一堆其他的程序，性能仅供参考
    import time

    start = time.time()

    # 运行单进程优化函数，自动输出结果，耗时：359秒
    # engine.runOptimization(AtrRsiStrategy, setting)

    # 多进程优化，耗时：89秒
    engine.runParallelOptimization(AtrRsiStrategy, setting)

    print u'耗时：%s' % (time.time() - start)

