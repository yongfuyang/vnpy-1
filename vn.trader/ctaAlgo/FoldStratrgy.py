# encoding: UTF-8

from ctaBase import *
from ctaTemplate import CtaTemplate
import talib
import numpy as np

class FOLDSTRATEGY(CtaTemplate):
    """
    策略基本思路是：如果连续两根K线收阳，就在两根K线的最高点回撤
    一定的幅度挂多单进场单，止盈为两根K线的最高点，止损为连根K线
    的最低点；做空策略相反。
    注意：测试策略，切勿实盘。后果自负
    """
    className = 'FOLDSTRATEGY'
    author = u'Chiang'

    # 策略参数
    Qty = 1                    # 交易数量
    upTrailingSet = 0.382      # 上涨回撤幅度
    dnTrailingSet = 0.5        # 下跌反弹幅度
    atrLength = 2

    # 策略变量
    bar = None
    barMinute = EMPTY_STRING


    initDays = 3

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'upTrailingSet',
                 'dnTrailingSet'
                 ]

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos'

               ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(FOLDSTRATEGY, self).__init__(ctaEngine, setting)

        """
        如果是多合约实例的话，变量需要放在这个地方
        """
        self.openArray = []  # 开盘价
        self.highArray = []  # 最高价
        self.lowArray = []  # 最低价
        self.closeArray = []  # 收盘价
        self.EntryOrder = []  # 进场指令存储
        self.ExitOrder = []  # 出场指令(进场指令在OnBar里面撤单，出场指令需要在OnTrade指令里面撤单，所以单独创建一个来存贮)

        self.LongeEntryPrice = EMPTY_FLOAT  # 多单进场价格
        self.LongProfitPrice = EMPTY_FLOAT  # 多单止盈价格
        self.LongStopPrice = EMPTY_FLOAT  # 多单止损价

        self.ShortEntryPrice = EMPTY_FLOAT  # 空单进场价格
        self.ShortProfitPrice = EMPTY_FLOAT  # 空单止盈价格
        self.ShortStopPrice = EMPTY_FLOAT  # 空单止损价格

        self.atrValue = 0
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s 策略初始化' %self.name)

        initData = self.loadBar(self.initDays)
        for bar in initData:
            self.onBar(bar)

        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s 策略启动' %self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s 策略停止' %self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""

        # 持有多单
        if self.pos == 1:
            # 挂出多单止盈
            if not self.ExitOrder:
                OrderID = self.sell(self.LongProfitPrice, self.Qty, stop=False)
                self.ExitOrder.append(OrderID)
            else:
                # 如果当前价格小于多单止损价，撤掉多单止盈单，立即平仓
                if tick.lastPrice < self.LongStopPrice:
                    for OrderID in self.ExitOrder:
                        self.cancelOrder(OrderID)
                    self.ExitOrder = []
                    self.sell(tick.lastPrice, self.Qty)

        # 持有空单
        if self.pos == -1:
            # 挂出空单止盈
            if not self.ExitOrder:
                OrderID = self.cover(self.ShortProfitPrice, self.Qty, stop=False)
                self.ExitOrder.append(OrderID)
            else:
                # 如果当前价格大于空单止损价 撤掉空单止盈，立即平仓
                if tick.lastPrice > self.ShortStopPrice:
                    for OrderID in self.ExitOrder:
                        self.cancelOrder(OrderID)
                    self.ExitOrder = []
                    self.cover(tick.lastPrice, self.Qty)

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
            bar.datetime = tick.datetime  # K线的时间设为第一个Tick的时间

            # 实盘中用不到的数据可以选择不算，从而加快速度
            bar.volume = tick.volume
            bar.openInterest = tick.openInterest

            self.bar = bar  # 这种写法为了减少一层访问，加快速度
            self.barMinute = tickMinute  # 更新当前的分钟

        else:  # 否则继续累加新的K线
            bar = self.bar  # 写法同样为了加快速度

            bar.high = max(bar.high, tick.lastPrice)
            bar.low = min(bar.low, tick.lastPrice)
            bar.close = tick.lastPrice

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""

        # 分别把开高低收几个价格存入数组e
        self.openArray.append(bar.open)
        if len(self.openArray) > 2:
            self.openArray.pop(0)

        self.highArray.append(bar.high)
        if len(self.highArray) > 2:
            self.highArray.pop(0)

        self.lowArray.append(bar.low)
        if len(self.lowArray) > 2:
            self.lowArray.pop(0)

        self.closeArray.append(bar.close)
        if len(self.closeArray) > 2:
            self.closeArray.pop(0)

        # 每个BAR来的时候，都撤掉以前的挂单，重新检查进场逻辑
        for orderID in self.EntryOrder:
            self.cancelOrder(orderID)
        self.EntryOrder = []

        # 等待数据缓存
        if len(self.closeArray) < 2 and len(self.openArray) < 2:
            return

        # 计算ATR的值
        self.atrValue = talib.ATR(np.array(self.highArray),
                                  np.array(self.lowArray),
                                  np.array(self.closeArray),
                                  self.atrLength)[-1]

        # 过滤掉波幅过小的时候
        if max(self.highArray[0],self.highArray[1]) - min(self.lowArray[0],self.lowArray[1]) < self.atrValue:
            return

        # 多空进场条件
        isLongEntryable = self.closeArray[0] > self.openArray[0] and self.closeArray[1] > self.openArray[1] and self.closeArray[1] > self.closeArray[0]
        isShortEntryable = self.closeArray[0] < self.openArray[0] and self.closeArray[1] < self.openArray[1] and self.closeArray[1] < self.closeArray[0]

        self.writeCtaLog(u'多单进场条件：' + str(isLongEntryable))
        self.writeCtaLog(u'空单进场条件：' + str(isShortEntryable))

        # 计算多单进出场价格
        if isLongEntryable:
            self.LongeEntryPrice = int(self.highArray[1] - (self.highArray[1] - self.lowArray[0])*self.upTrailingSet)
            self.LongProfitPrice = max(self.highArray[1],self.highArray[0])
            self.LongStopPrice = min(self.lowArray[0],self.lowArray[1])

            self.writeCtaLog(u'多单进场价：' + str(self.LongeEntryPrice))
            self.writeCtaLog(u'多单止盈价：' + str(self.LongProfitPrice))
            self.writeCtaLog(u'多单止损价：' + str(self.LongStopPrice))

        # 计算空单进出场价格
        if isShortEntryable:
            self.ShortEntryPrice = int(self.lowArray[1] + (self.highArray[0] - self.lowArray[1])*self.dnTrailingSet)
            self.ShortProfitPrice = min(self.lowArray[0],self.lowArray[1])
            self.ShortStopPrice = max(self.highArray[0],self.highArray[1])

            self.writeCtaLog(u'空单进场价：' + str(self.ShortEntryPrice))
            self.writeCtaLog(u'空单止盈价：' + str(self.ShortProfitPrice))
            self.writeCtaLog(u'空单止损价：' + str(self.ShortStopPrice))

        # 多单进场
        if isLongEntryable:
             if self.pos == 0:                                         # 无持仓直接开多
                 orderID = self.buy(self.LongeEntryPrice,self.Qty)
                 self.EntryOrder.append(orderID)
             elif self.pos == -1:                                      # 有空单先平仓再开多
                 self.cover(bar.close,self.Qty)
                 orderID = self.buy(self.LongeEntryPrice, self.Qty)
                 self.EntryOrder.append(orderID)

        # 空单进场
        if isShortEntryable:
            if self.pos == 0:                                          # 无持仓直接开空
                orderID = self.short(self.ShortEntryPrice,self.Qty)
                self.EntryOrder.append(orderID)
            elif self.pos == 1:                                        # 有多单先平多再开空
                self.sell(bar.close,self.Qty)
                orderID = self.short(self.ShortEntryPrice,self.Qty)
                self.EntryOrder.append(orderID)

        # 发出状态更新事件
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder

        pass

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        pass

        # 发出状态更新事件
        # self.putEvent()
    # ===============================================================




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
    engine.setStartDate('20120101')

    # 设置产品相关参数
    engine.setSlippage(0.2)     # 股指1跳
    engine.setRate(0.3/10000)   # 万0.3
    engine.setSize(15)         # 股指合约大小

    # 设置使用的历史数据库
    engine.setDatabase(MINUTE_DB_NAME, 'ag1612')

    # 在引擎中创建策略对象
    engine.initStrategy(FOLDSTRATEGY, {})

    # 开始跑回测
    engine.runBacktesting()

    # 显示回测结果
    engine.showBacktestingResult()

    # # 跑优化
    # setting = OptimizationSetting()                 # 新建一个优化任务设置对象
    # setting.setOptimizeTarget('capital')            # 设置优化排序的目标是策略净盈利
    # setting.addParameter('atrLength', 11, 12, 1)    # 增加第一个优化参数atrLength，起始11，结束12，步进1
    # setting.addParameter('atrMa', 20, 30, 5)        # 增加第二个优化参数atrMa，起始20，结束30，步进1
    # engine.runOptimization(AtrRsiStrategy, setting) # 运行优化函数，自动输出结果
