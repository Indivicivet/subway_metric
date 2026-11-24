export const cities = {
  taipei: {
    name: "台北 (Taipei)",
    mode: "MRT",
    start: [121.517, 25.0468],
    view: [[121.418, 24.956], [121.631, 25.174]],
    credit: "MRT data",
    shortLineLabels: true,
  },
  london: {
    name: "London",
    mode: "Tube",
    start: [-0.12765, 51.50797],
    view: [[-0.614, 51.397], [0.253, 51.709]],
    credit: "Powered by TfL Open Data",
  },
  guangzhou: {
    name: "广州 (Guangzhou)",
    mode: "Metro",
    start: [113.3158725, 23.1219809],
    view: [[113.09, 22.75], [113.87, 23.62]],
    minZoom: 8.5,
    credit: "Guangzhou data and estimates",
    timeLabel: "Estimated weekday",
  },
  zhengzhou: {
    name: "郑州 (Zhengzhou)", mode: "Metro", start: [113.6654, 34.7566],
    view: [[112.95, 33.95], [114.25, 35.05]], minZoom: 8,
    credit: "Zhengzhou data and estimates", timeLabel: "Estimated weekday",
  },
  shanghai: {
    name: "上海 (Shanghai)", mode: "Metro", start: [121.4737, 31.2304],
    view: [[120.90, 30.72], [122.00, 31.72]], minZoom: 8,
    credit: "Shanghai data and estimates", timeLabel: "Estimated weekday",
  },
  chongqing: {
    name: "重庆 (Chongqing)", mode: "Metro", start: [106.55, 29.56],
    view: [[105.95, 29.05], [107.00, 30.15]], minZoom: 8,
    credit: "Chongqing data and estimates", timeLabel: "Estimated weekday",
  },
  chengdu: {
    name: "成都 (Chengdu)", mode: "Metro", start: [104.0665, 30.657],
    view: [[103.65, 30.05], [104.85, 31.05]], minZoom: 8,
    credit: "Chengdu data and estimates", timeLabel: "Estimated weekday",
  },
  beijing: {
    name: "北京 (Beijing)", mode: "Subway", start: [116.397, 39.909],
    view: [[115.75, 39.35], [117.15, 40.35]], minZoom: 8,
    credit: "Beijing data and estimates", timeLabel: "Estimated weekday",
  },
  qingdao: {
    name: "青岛 (Qingdao)", mode: "Metro", start: [120.3753, 36.0646],
    view: [[119.65, 35.50], [121.10, 36.65]], minZoom: 8,
    credit: "Qingdao data and estimates", timeLabel: "Estimated weekday",
  },
  shenzhen: {
    name: "深圳 (Shenzhen)", mode: "Metro", start: [114.0579, 22.5431],
    view: [[113.70, 22.40], [114.70, 22.95]], minZoom: 8,
    credit: "Shenzhen data and estimates", timeLabel: "Estimated weekday",
  },
  wuhan: {
    name: "武汉 (Wuhan)", mode: "Metro", start: [114.305, 30.593],
    view: [[113.85, 30.25], [114.65, 30.85]], minZoom: 8,
    credit: "Wuhan data and estimates", timeLabel: "Estimated weekday",
  },
  changsha: {
    name: "长沙 (Changsha)", mode: "Metro", start: [112.979, 28.195],
    view: [[112.75, 27.95], [113.25, 28.35]], minZoom: 8.5,
    credit: "Changsha data and estimates", timeLabel: "Estimated weekday",
  },
  singapore: {
    name: "Singapore", mode: "MRT", start: [103.851, 1.299],
    view: [[103.62, 1.24], [104.02, 1.46]], minZoom: 9.5,
    credit: "Singapore data and estimates", timeLabel: "Estimated weekday",
    shortLineLabels: true,
  },
  seoul: {
    name: "Seoul", mode: "Subway", start: [126.978, 37.566],
    view: [[126.65, 37.35], [127.25, 37.75]], minZoom: 8.5,
    credit: "Seoul data and estimates", timeLabel: "Estimated weekday",
  },
  tokyo: {
    name: "東京 (Tokyo)", mode: "Subway", start: [139.767, 35.681],
    view: [[139.55, 35.55], [139.95, 35.85]], minZoom: 9,
    credit: "Tokyo data and estimates", timeLabel: "Estimated weekday",
    shortLineLabels: true,
  },
  osaka: {
    name: "大阪 (Osaka)", mode: "Metro", start: [135.498, 34.693],
    view: [[135.38, 34.54], [135.62, 34.80]], minZoom: 9.5,
    credit: "Osaka data and estimates", timeLabel: "Estimated weekday",
    shortLineLabels: true,
  },
  nagoya: {
    name: "名古屋 (Nagoya)", mode: "Subway", start: [136.906, 35.170],
    view: [[136.78, 35.04], [137.05, 35.28]], minZoom: 9.5,
    credit: "Nagoya data and estimates", timeLabel: "Estimated weekday",
    shortLineLabels: true,
  },
  kyoto: {
    name: "京都 (Kyoto)", mode: "Subway", start: [135.759, 35.004],
    view: [[135.66, 34.90], [135.86, 35.10]], minZoom: 10,
    credit: "Kyoto data and estimates", timeLabel: "Estimated weekday",
    shortLineLabels: true,
  },
};

export const defaultCity = "taipei";
