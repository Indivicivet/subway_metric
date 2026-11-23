export const cities = {
  taipei: {
    name: "Taipei",
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
    name: "Guangzhou",
    mode: "Metro",
    start: [113.3158725, 23.1219809],
    view: [[113.09, 22.75], [113.87, 23.62]],
    minZoom: 8.5,
    credit: "Guangzhou data and estimates",
    timeLabel: "Estimated weekday",
  },
  zhengzhou: {
    name: "Zhengzhou", mode: "Metro", start: [113.6654, 34.7566],
    view: [[112.95, 33.95], [114.25, 35.05]], minZoom: 8,
    credit: "Zhengzhou data and estimates", timeLabel: "Estimated weekday",
  },
  shanghai: {
    name: "Shanghai", mode: "Metro", start: [121.4737, 31.2304],
    view: [[120.90, 30.72], [122.00, 31.72]], minZoom: 8,
    credit: "Shanghai data and estimates", timeLabel: "Estimated weekday",
  },
  chongqing: {
    name: "Chongqing", mode: "Metro", start: [106.55, 29.56],
    view: [[105.95, 29.05], [107.00, 30.15]], minZoom: 8,
    credit: "Chongqing data and estimates", timeLabel: "Estimated weekday",
  },
  chengdu: {
    name: "Chengdu", mode: "Metro", start: [104.0665, 30.657],
    view: [[103.65, 30.05], [104.85, 31.05]], minZoom: 8,
    credit: "Chengdu data and estimates", timeLabel: "Estimated weekday",
  },
  beijing: {
    name: "Beijing", mode: "Subway", start: [116.397, 39.909],
    view: [[115.75, 39.35], [117.15, 40.35]], minZoom: 8,
    credit: "Beijing data and estimates", timeLabel: "Estimated weekday",
  },
  qingdao: {
    name: "Qingdao", mode: "Metro", start: [120.3753, 36.0646],
    view: [[119.65, 35.50], [121.10, 36.65]], minZoom: 8,
    credit: "Qingdao data and estimates", timeLabel: "Estimated weekday",
  },
  shenzhen: {
    name: "Shenzhen", mode: "Metro", start: [114.0579, 22.5431],
    view: [[113.70, 22.40], [114.70, 22.95]], minZoom: 8,
    credit: "Shenzhen data and estimates", timeLabel: "Estimated weekday",
  },
};

export const defaultCity = "taipei";
