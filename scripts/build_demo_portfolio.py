"""生成独立编写的产品方案配图；仅素材构建时需要matplotlib。"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.font_manager import FontProperties

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'web/demo-portfolio';out.mkdir(exist_ok=True)
    font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    plt.rcParams['font.family']=font.get_name()
    cases=[('video-workflow','AI视频工作流 · 产品方案','从内容目标到团队协同，让创作过程清晰可控。',
            [('选题与目标','受众画像 / 内容定位'),('脚本与角色','脚本版本 / 角色分工'),('分镜与素材','素材检索 / 镜头编排'),('生成与合成','任务队列 / 失败重试'),('审阅与发布','人工确认 / 版本追踪'),('效果与复盘','播放反馈 / 任务改进')]),
           ('research-agent','投研智能体 · 产品方案','围绕证据、引用与复核组织研究任务。',
            [('研究问题','行业范围 / 任务拆解'),('资料检索','来源筛选 / 权限核对'),('证据整理','事实摘录 / 数据对齐'),('研究分析','比较框架 / 分歧记录'),('引用复核','原文定位 / 结果确认'),('报告工作台','文稿版本 / 协作交付')])]
    for slug,title,sub,nodes in cases:
        fig=plt.figure(figsize=(12,7.2),facecolor='#F2F7F5');ax=fig.add_axes([0,0,1,1]);ax.set_xlim(0,12);ax.set_ylim(0,7.2);ax.axis('off')
        ax.text(.7,6.55,'PRODUCT DESIGN  /  蔡雨轩',color='#4F9E94',fontsize=12,weight='bold')
        ax.text(.7,5.95,title,color='#173F50',fontsize=27,weight='bold')
        ax.text(.7,5.48,sub,color='#6F858C',fontsize=13)
        positions=[(.7,3.65),(4.6,3.65),(8.5,3.65),(8.5,1.25),(4.6,1.25),(.7,1.25)]
        for i,((name,desc),(x,y)) in enumerate(zip(nodes,positions)):
            box=FancyBboxPatch((x,y),2.8,1.4,boxstyle='round,pad=.12,rounding_size=.16',facecolor='#FFFFFF',edgecolor='#B8D5CC',linewidth=1.4);ax.add_patch(box)
            ax.text(x+.15,y+1.03,f'0{i+1}',color='#C29949',fontsize=14,weight='bold');ax.text(x+.15,y+.66,name,color='#1B635B',fontsize=18,weight='bold');ax.text(x+.15,y+.22,desc,color='#73888C',fontsize=11)
        for i in [0,1]:ax.add_patch(FancyArrowPatch((positions[i][0]+2.93,4.35),(positions[i+1][0]-.2,4.35),arrowstyle='-|>',mutation_scale=20,color='#81ADA1',linewidth=2))
        ax.add_patch(FancyArrowPatch((9.9,3.5),(9.9,2.8),arrowstyle='-|>',mutation_scale=20,color='#81ADA1',linewidth=2))
        for i in [3,4]:ax.add_patch(FancyArrowPatch((positions[i][0]-.2,1.95),(positions[i+1][0]+2.93,1.95),arrowstyle='-|>',mutation_scale=20,color='#81ADA1',linewidth=2))
        ax.text(.7,.45,'设计重点：任务可拆解 · 过程可追踪 · 结果可复核',color='#6F858C',fontsize=12)
        fig.savefig(out/(slug+'.png'),dpi=180);plt.close(fig)


if __name__=='__main__':main()
